"""Password strength policy and pwned-password checking.

Length-based strength, no composition or rotation rules, plus a k-anonymity
breach check against Have I Been Pwned that fails open. Enforced wherever a
password is set.

Every rule here comes from [OWASP ASVS v4, chapter V2.1][asvs]:

| Requirement | Where it lives |
| --- | --- |
| 2.1.1 — at least 12 characters | `MIN_LENGTH_BY_STRENGTH[MEDIUM]`, the default tier |
| 2.1.2 — permit 64, deny past 128 | `AuthConfig.PASSWORD_MAX_LENGTH` (`default=128, ge=64`) |
| 2.1.7 — breach check | `validate_password_strength` via `PwnedPasswordChecker` |
| 2.1.9 — no composition rules | nothing here inspects character classes |
| 2.1.10 — no periodic rotation | no password expiry anywhere in the app |

[asvs]: https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x11-V2-Authentication.md
"""

import hashlib
from typing import Protocol

import httpx

from backend.auth.config import AuthConfig, PasswordStrength
from backend.auth.exceptions import PasswordCompromised, PasswordTooLong, PasswordTooShort

MIN_LENGTH_BY_STRENGTH: dict[PasswordStrength, int] = {
    PasswordStrength.LOW: 8,
    PasswordStrength.MEDIUM: 12,
    PasswordStrength.HIGH: 15,
}

_HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{}"


class PwnedPasswordChecker(Protocol):
    async def is_pwned(self, password: str) -> bool: ...


async def validate_password_strength(
    password: str,
    *,
    config: AuthConfig,
    pwned_checker: PwnedPasswordChecker,
) -> None:
    """Raise if `password` violates the active policy.

    Raises:
        PasswordTooShort: shorter than the active strength floor.
        PasswordTooLong: longer than `config.PASSWORD_MAX_LENGTH`.
        PasswordCompromised: found in a known breach.
    """
    if len(password) < MIN_LENGTH_BY_STRENGTH[config.PASSWORD_STRENGTH]:
        raise PasswordTooShort
    if len(password) > config.PASSWORD_MAX_LENGTH:
        raise PasswordTooLong

    if not config.PASSWORD_CHECK_PWNED:
        return
    if await pwned_checker.is_pwned(password):
        raise PasswordCompromised


class HIBPPwnedPasswordChecker:
    """Have I Been Pwned [range-API][api] checker using [k-anonymity][kanon].

    Only the first 5 hex chars of the password's SHA-1 digest leave the process:
    the service answers with every hash sharing that prefix and never learns
    which one was asked about. SHA-1 is the API's choice of digest, not this
    app's password hash, which is argon2.

    Fails open: any transport error or non-200 counts as "not pwned", so a HIBP
    outage never blocks a password change.

    [api]: https://haveibeenpwned.com/API/v3#SearchingPwnedPasswordsByRange
    [kanon]: https://blog.cloudflare.com/validating-leaked-passwords-with-k-anonymity/
    """

    def __init__(self, *, client: httpx.AsyncClient) -> None:
        self._client = client

    async def is_pwned(self, password: str) -> bool:
        digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]

        try:
            response = await self._client.get(_HIBP_RANGE_URL.format(prefix))
        except httpx.HTTPError:
            return False
        if response.status_code != 200:
            return False

        for line in response.text.splitlines():
            candidate, _, count = line.partition(":")
            if count.strip() == "0":
                continue  # Add-Padding fabricated entry - not a real breach hit
            if candidate.strip().upper() == suffix:
                return True
        return False
