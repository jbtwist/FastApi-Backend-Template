"""Password strength policy (OWASP ASVS v4 2.1.x) and pwned-password checking."""

import hashlib
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from backend.auth import password_policy
from backend.auth.config import AuthConfig, PasswordStrength
from backend.auth.exceptions import PasswordCompromised, PasswordTooLong, PasswordTooShort

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"

LOW_MIN_LENGTH = 8
MEDIUM_MIN_LENGTH = 12
HIGH_MIN_LENGTH = 15


def _config(
    strength: PasswordStrength = PasswordStrength.MEDIUM,
    *,
    max_length: int = 128,
    check_pwned: bool = True,
) -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        PASSWORD_STRENGTH=strength,
        PASSWORD_MAX_LENGTH=max_length,
        PASSWORD_CHECK_PWNED=check_pwned,
    )


@pytest.fixture
def policy_config() -> AuthConfig:
    return _config(PasswordStrength.MEDIUM, max_length=64)


@pytest.fixture
def clean_checker() -> AsyncMock:
    checker = AsyncMock()
    checker.is_pwned.return_value = False
    return checker


class TestAuthConfigPasswordMaxLength:
    """ASVS 2.1.2: at least 64-char passwords must be permitted, so a misconfigured
    PASSWORD_MAX_LENGTH can't silently violate that floor."""

    def test_rejects_a_max_length_below_the_asvs_floor(self):
        with pytest.raises(ValidationError):
            AuthConfig(JWT_SECRET=TEST_JWT_SECRET, PASSWORD_MAX_LENGTH=63)

    def test_accepts_a_max_length_at_the_asvs_floor(self):
        assert (
            AuthConfig(JWT_SECRET=TEST_JWT_SECRET, PASSWORD_MAX_LENGTH=64).PASSWORD_MAX_LENGTH == 64
        )

    def test_accepts_a_max_length_well_above_the_floor(self):
        assert (
            AuthConfig(JWT_SECRET=TEST_JWT_SECRET, PASSWORD_MAX_LENGTH=256).PASSWORD_MAX_LENGTH
            == 256
        )

    def test_default_max_length_is_128(self):
        assert AuthConfig(JWT_SECRET=TEST_JWT_SECRET).PASSWORD_MAX_LENGTH == 128


class TestPasswordStrengthTiers:
    def test_exposes_the_documented_min_length_per_tier(self):
        assert password_policy.MIN_LENGTH_BY_STRENGTH == {
            PasswordStrength.LOW: LOW_MIN_LENGTH,
            PasswordStrength.MEDIUM: MEDIUM_MIN_LENGTH,
            PasswordStrength.HIGH: HIGH_MIN_LENGTH,
        }


class TestValidatePasswordStrength:
    @pytest.mark.parametrize(
        ("strength", "min_length"),
        [
            (PasswordStrength.LOW, LOW_MIN_LENGTH),
            (PasswordStrength.MEDIUM, MEDIUM_MIN_LENGTH),
            (PasswordStrength.HIGH, HIGH_MIN_LENGTH),
        ],
    )
    async def test_accepts_a_password_at_exactly_the_tier_minimum(
        self, clean_checker, strength, min_length
    ):
        await password_policy.validate_password_strength(
            "a" * min_length, config=_config(strength), pwned_checker=clean_checker
        )

    @pytest.mark.parametrize(
        ("strength", "min_length"),
        [
            (PasswordStrength.LOW, LOW_MIN_LENGTH),
            (PasswordStrength.MEDIUM, MEDIUM_MIN_LENGTH),
            (PasswordStrength.HIGH, HIGH_MIN_LENGTH),
        ],
    )
    async def test_rejects_a_password_one_char_short(self, clean_checker, strength, min_length):
        with pytest.raises(PasswordTooShort):
            await password_policy.validate_password_strength(
                "a" * (min_length - 1), config=_config(strength), pwned_checker=clean_checker
            )

    async def test_accepts_a_password_at_exactly_the_max_length(self, policy_config, clean_checker):
        await password_policy.validate_password_strength(
            "a" * policy_config.PASSWORD_MAX_LENGTH,
            config=policy_config,
            pwned_checker=clean_checker,
        )

    async def test_rejects_a_password_over_the_max_length(self, policy_config, clean_checker):
        with pytest.raises(PasswordTooLong):
            await password_policy.validate_password_strength(
                "a" * (policy_config.PASSWORD_MAX_LENGTH + 1),
                config=policy_config,
                pwned_checker=clean_checker,
            )

    async def test_does_not_call_the_pwned_checker_when_too_short(
        self, policy_config, clean_checker
    ):
        with pytest.raises(PasswordTooShort):
            await password_policy.validate_password_strength(
                "short", config=policy_config, pwned_checker=clean_checker
            )
        clean_checker.is_pwned.assert_not_called()

    async def test_rejects_a_password_reported_as_pwned(self, policy_config):
        checker = AsyncMock()
        checker.is_pwned.return_value = True

        with pytest.raises(PasswordCompromised):
            await password_policy.validate_password_strength(
                "correct-horse-battery", config=policy_config, pwned_checker=checker
            )

    async def test_accepts_a_clean_password_and_awaits_the_checker_once(
        self, policy_config, clean_checker
    ):
        await password_policy.validate_password_strength(
            "correct-horse-battery", config=policy_config, pwned_checker=clean_checker
        )
        clean_checker.is_pwned.assert_awaited_once_with("correct-horse-battery")

    async def test_skips_the_pwned_check_when_disabled_in_config(
        self, policy_config, clean_checker
    ):
        disabled = policy_config.model_copy(update={"PASSWORD_CHECK_PWNED": False})

        await password_policy.validate_password_strength(
            "correct-horse-battery", config=disabled, pwned_checker=clean_checker
        )
        clean_checker.is_pwned.assert_not_called()


def _sha1_prefix_suffix(password: str) -> tuple[str, str]:
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    return digest[:5], digest[5:]


class TestHIBPPwnedPasswordChecker:
    """k-anonymity: only a 5-char SHA-1 prefix leaves the process (ASVS 2.1.7)."""

    async def test_sends_only_the_five_char_sha1_prefix(self):
        prefix, _ = _sha1_prefix_suffix("correct-horse-battery")
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, text="")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        await checker.is_pwned("correct-horse-battery")

        assert len(seen) == 1
        assert seen[0].url.path == f"/range/{prefix}"
        assert "correct-horse-battery" not in str(seen[0].url)

    async def test_returns_true_when_the_suffix_is_present(self):
        _, suffix = _sha1_prefix_suffix("correct-horse-battery")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=f"{suffix}:3730\nAAAA1111AAAA1111AAAA1111AAAA1111AAA:1")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is True

    async def test_returns_false_when_the_suffix_is_absent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="AAAA1111AAAA1111AAAA1111AAAA1111AAA:1")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is False

    async def test_matches_the_suffix_case_insensitively(self):
        _, suffix = _sha1_prefix_suffix("correct-horse-battery")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=f"{suffix.lower()}:3730")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is True

    async def test_ignores_padding_lines_with_a_zero_count(self):
        _, suffix = _sha1_prefix_suffix("correct-horse-battery")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=f"{suffix}:0")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is False

    async def test_fails_open_when_the_api_is_unreachable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is False

    async def test_fails_open_on_a_non_200_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="")

        checker = password_policy.HIBPPwnedPasswordChecker(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
        assert await checker.is_pwned("correct-horse-battery") is False
