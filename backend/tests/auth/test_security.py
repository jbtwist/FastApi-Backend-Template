import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta

import jwt
import jwt.api_jwt
import pytest
from argon2 import PasswordHasher

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
    async def test_hash_password_returns_argon2id_hash(self):
        hashed = await security.hash_password("correct horse battery staple")

        assert hashed.startswith("$argon2id$")

    async def test_hash_password_produces_different_hash_for_same_password(self):
        hashed_1 = await security.hash_password("correct horse battery staple")
        hashed_2 = await security.hash_password("correct horse battery staple")

        assert hashed_1 != hashed_2

    async def test_verify_password_succeeds_for_correct_password(self):
        hashed = await security.hash_password("correct horse battery staple")

        assert await security.verify_password("correct horse battery staple", hashed) is True

    async def test_verify_password_fails_for_incorrect_password(self):
        hashed = await security.hash_password("correct horse battery staple")

        assert await security.verify_password("wrong password", hashed) is False

    async def test_verify_password_fails_for_malformed_hash(self):
        assert await security.verify_password("anything", "not-a-real-hash") is False

    async def test_hash_password_roundtrips_very_long_password(self):
        long_password = "p" * 5000
        hashed = await security.hash_password(long_password)

        assert await security.verify_password(long_password, hashed) is True

    async def test_hash_password_roundtrips_unicode_password(self):
        password = "correct-horse-🔒-battery-日本語"
        hashed = await security.hash_password(password)

        assert await security.verify_password(password, hashed) is True


class _ThreadRecordingHasher:
    """Stand-in for the argon2 hasher that records which thread called it."""

    def __init__(self) -> None:
        self.thread_id: int | None = None

    def hash(self, password: str) -> str:
        self.thread_id = threading.get_ident()
        return "$argon2id$stub"

    def verify(self, password_hash: str, password: str) -> bool:
        self.thread_id = threading.get_ident()
        return True


class TestPasswordHashingStaysOffTheEventLoop:
    async def test_hash_password_runs_in_a_worker_thread(self, monkeypatch):
        hasher = _ThreadRecordingHasher()
        monkeypatch.setattr(security, "_password_hasher", hasher)

        await security.hash_password("correct horse battery staple")

        assert hasher.thread_id is not None
        assert hasher.thread_id != threading.get_ident()

    async def test_verify_password_runs_in_a_worker_thread(self, monkeypatch):
        hasher = _ThreadRecordingHasher()
        monkeypatch.setattr(security, "_password_hasher", hasher)

        await security.verify_password("correct horse battery staple", "$argon2id$stub")

        assert hasher.thread_id is not None
        assert hasher.thread_id != threading.get_ident()

    async def test_other_tasks_make_progress_during_a_real_hash(self):
        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                ticks += 1
                await asyncio.sleep(0.001)

        task = asyncio.create_task(ticker())
        await security.hash_password("correct horse battery staple")
        task.cancel()

        assert ticks > 1


class TestPasswordHashingCost:
    """The cost parameters are a security setting, so a change has to be deliberate."""

    async def test_hash_records_the_owasp_minimum_parameters(self):
        hashed = await security.hash_password("correct horse battery staple")

        assert "$m=19456,t=2,p=1$" in hashed

    async def test_a_hash_made_with_the_previous_parameters_still_verifies(self):
        """Parameters live in the hash string, so stored hashes need no migration."""
        legacy = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4).hash("pw")

        assert await security.verify_password("pw", legacy) is True


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


class TestOpaqueToken:
    """`generate_opaque_token` / `hash_opaque_token` back the refresh,
    email-verification and password-reset token tables alike."""

    def test_generate_returns_url_safe_string(self):
        raw = security.generate_opaque_token()

        assert isinstance(raw, str)
        assert len(raw) >= 32

    def test_generate_is_unique_across_calls(self):
        assert security.generate_opaque_token() != security.generate_opaque_token()

    def test_hash_is_deterministic(self):
        raw = "some-raw-token-value"

        assert security.hash_opaque_token(raw) == security.hash_opaque_token(raw)

    def test_hash_differs_for_different_input(self):
        assert security.hash_opaque_token("token-a") != security.hash_opaque_token("token-b")

    def test_hash_does_not_return_raw_value(self):
        raw = "some-raw-token-value"

        assert security.hash_opaque_token(raw) != raw


class TestMinimumDuration:
    """The response floor every enumeration-safe endpoint relies on."""

    async def test_pads_fast_work_up_to_the_minimum(self):
        start = time.perf_counter()

        async with security.minimum_duration(timedelta(milliseconds=50)):
            pass

        assert time.perf_counter() - start >= 0.05

    async def test_pads_even_when_the_work_raises(self):
        start = time.perf_counter()

        with pytest.raises(RuntimeError):
            async with security.minimum_duration(timedelta(milliseconds=50)):
                raise RuntimeError

        assert time.perf_counter() - start >= 0.05

    async def test_adds_no_delay_when_the_minimum_is_zero(self):
        start = time.perf_counter()

        async with security.minimum_duration(timedelta(0)):
            pass

        assert time.perf_counter() - start < 0.05
