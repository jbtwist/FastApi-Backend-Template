"""Password strength policy (OWASP ASVS v4 2.1.x) and pwned-password checking.

Length-based strength with a generous maximum, no composition or rotation rules,
plus a k-anonymity breach check against Have I Been Pwned that fails open.
Enforced wherever a password is set (registration, password reset).
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

    Checks in order: too short -> too long -> found in a breach. The breach check
    is skipped when the password already failed a length check or when
    `config.PASSWORD_CHECK_PWNED` is `False`; otherwise `pwned_checker.is_pwned`
    is awaited exactly once with the raw password.

    Raises:
        PasswordTooShort / PasswordTooLong / PasswordCompromised
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
    """Have I Been Pwned range-API checker using k-anonymity.

    Only the first 5 hex chars of the password's SHA-1 digest leave the process
    (ASVS 2.1.7). Fails open: any transport error or non-200 response is treated
    as "not pwned", so a HIBP outage never blocks a password change.
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
