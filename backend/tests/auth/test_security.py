from datetime import UTC, datetime, timedelta

import jwt
import jwt.api_jwt
import pytest

from backend.auth import security
from backend.auth.config import AuthConfig
from backend.auth.exceptions import AccessTokenExpired, InvalidAccessToken

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"
OTHER_JWT_SECRET = "other-secret-123456789012345678901234567890123456789012345678901"
TEST_USER_ID = "12345678-1234-5678-1234-567812345678"


@pytest.fixture
def auth_config() -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        JWT_ALG="HS256",
        ACCESS_TOKEN_EXP=timedelta(days=1),
        REFRESH_TOKEN_EXP=timedelta(days=7),
        COOKIE_SECURE=True,
    )


@pytest.fixture
def freeze_time(monkeypatch):
    """Freeze the wall clock PyJWT reads for exp/iat checks, so tests stay
    deterministic without depending on real time passing."""

    def _freeze(moment: datetime) -> None:
        class FrozenDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return moment if tz is None else moment.astimezone(tz)

        monkeypatch.setattr(jwt.api_jwt, "datetime", FrozenDatetime)

    return _freeze


class TestPasswordHashing:
    def test_hash_password_returns_argon2id_hash(self):
        hashed = security.hash_password("correct horse battery staple")

        assert hashed.startswith("$argon2id$")

    def test_hash_password_produces_different_hash_for_same_password(self):
        hashed_1 = security.hash_password("correct horse battery staple")
        hashed_2 = security.hash_password("correct horse battery staple")

        assert hashed_1 != hashed_2

    def test_verify_password_succeeds_for_correct_password(self):
        hashed = security.hash_password("correct horse battery staple")

        assert security.verify_password("correct horse battery staple", hashed) is True

    def test_verify_password_fails_for_incorrect_password(self):
        hashed = security.hash_password("correct horse battery staple")

        assert security.verify_password("wrong password", hashed) is False

    def test_verify_password_fails_for_malformed_hash(self):
        assert security.verify_password("anything", "not-a-real-hash") is False

    def test_hash_password_roundtrips_very_long_password(self):
        long_password = "p" * 5000
        hashed = security.hash_password(long_password)

        assert security.verify_password(long_password, hashed) is True

    def test_hash_password_roundtrips_unicode_password(self):
        password = "correct-horse-🔒-battery-日本語"
        hashed = security.hash_password(password)

        assert security.verify_password(password, hashed) is True


class TestAccessToken:
    def test_create_access_token_contains_expected_claims(self, auth_config):
        now = datetime(2026, 1, 1, tzinfo=UTC)

        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)
        payload = jwt.decode(
            token, TEST_JWT_SECRET, algorithms=["HS256"], options={"verify_exp": False}
        )

        assert payload["sub"] == TEST_USER_ID
        assert payload["iat"] == int(now.timestamp())
        assert payload["exp"] == int((now + auth_config.ACCESS_TOKEN_EXP).timestamp())

    def test_decode_access_token_returns_payload_for_valid_token(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)

        freeze_time(now)
        payload = security.decode_access_token(token, config=auth_config)

        assert payload["sub"] == TEST_USER_ID

    def test_decode_access_token_raises_when_expired(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)
        past_expiry = now + auth_config.ACCESS_TOKEN_EXP + timedelta(seconds=1)

        freeze_time(past_expiry)
        with pytest.raises(AccessTokenExpired):
            security.decode_access_token(token, config=auth_config)

    def test_decode_access_token_raises_for_tampered_token(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)
        tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(tampered, config=auth_config)

    def test_decode_access_token_raises_for_wrong_secret(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)
        wrong_config = auth_config.model_copy(update={"JWT_SECRET": OTHER_JWT_SECRET})

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(token, config=wrong_config)

    def test_decode_access_token_raises_for_garbage_string(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token("not-a-jwt-at-all", config=auth_config)

    def test_decode_access_token_raises_exactly_at_expiry_instant(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token = security.create_access_token(TEST_USER_ID, config=auth_config, now=now)
        exact_expiry = now + auth_config.ACCESS_TOKEN_EXP

        freeze_time(exact_expiry)
        with pytest.raises(AccessTokenExpired):
            security.decode_access_token(token, config=auth_config)

    def test_decode_access_token_rejects_token_signed_with_different_algorithm(
        self, auth_config, freeze_time
    ):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        mismatched_token = jwt.encode(
            {
                "sub": TEST_USER_ID,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(days=1)).timestamp()),
            },
            TEST_JWT_SECRET,
            algorithm="HS512",
        )

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(mismatched_token, config=auth_config)

    def test_decode_access_token_raises_when_sub_claim_is_missing(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token_without_sub = jwt.encode(
            {"iat": int(now.timestamp()), "exp": int((now + timedelta(days=1)).timestamp())},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(token_without_sub, config=auth_config)

    def test_decode_access_token_raises_when_sub_claim_is_not_a_uuid(
        self, auth_config, freeze_time
    ):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token_with_bad_sub = jwt.encode(
            {
                "sub": "not-a-uuid",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(days=1)).timestamp()),
            },
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(token_with_bad_sub, config=auth_config)

    def test_decode_access_token_raises_when_sub_claim_is_not_a_string(
        self, auth_config, freeze_time
    ):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token_with_non_string_sub = jwt.encode(
            {
                "sub": 12345,
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(days=1)).timestamp()),
            },
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(token_with_non_string_sub, config=auth_config)

    def test_decode_access_token_raises_when_exp_claim_is_missing(self, auth_config, freeze_time):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        token_without_exp = jwt.encode(
            {"sub": TEST_USER_ID, "iat": int(now.timestamp())},
            TEST_JWT_SECRET,
            algorithm="HS256",
        )

        freeze_time(now)
        with pytest.raises(InvalidAccessToken):
            security.decode_access_token(token_without_exp, config=auth_config)


class TestRefreshTokenValue:
    def test_generate_refresh_token_returns_url_safe_string(self, auth_config):
        raw = security.generate_refresh_token(config=auth_config)

        assert isinstance(raw, str)
        assert len(raw) >= 32

    def test_generate_refresh_token_is_unique_across_calls(self, auth_config):
        first = security.generate_refresh_token(config=auth_config)
        second = security.generate_refresh_token(config=auth_config)

        assert first != second

    def test_hash_refresh_token_is_deterministic(self):
        raw = "some-raw-refresh-token-value"

        assert security.hash_refresh_token(raw) == security.hash_refresh_token(raw)

    def test_hash_refresh_token_differs_for_different_input(self):
        assert security.hash_refresh_token("token-a") != security.hash_refresh_token("token-b")

    def test_hash_refresh_token_does_not_return_raw_value(self):
        raw = "some-raw-refresh-token-value"

        assert security.hash_refresh_token(raw) != raw


class TestEmailVerificationTokenValue:
    def test_generate_email_verification_token_returns_url_safe_string(self, auth_config):
        raw = security.generate_email_verification_token(config=auth_config)

        assert isinstance(raw, str)
        assert len(raw) >= 32

    def test_generate_email_verification_token_is_unique_across_calls(self, auth_config):
        first = security.generate_email_verification_token(config=auth_config)
        second = security.generate_email_verification_token(config=auth_config)

        assert first != second

    def test_hash_email_verification_token_is_deterministic(self):
        raw = "some-raw-verification-token-value"

        assert security.hash_email_verification_token(
            raw
        ) == security.hash_email_verification_token(raw)

    def test_hash_email_verification_token_differs_for_different_input(self):
        assert security.hash_email_verification_token(
            "token-a"
        ) != security.hash_email_verification_token("token-b")

    def test_hash_email_verification_token_does_not_return_raw_value(self):
        raw = "some-raw-verification-token-value"

        assert security.hash_email_verification_token(raw) != raw
