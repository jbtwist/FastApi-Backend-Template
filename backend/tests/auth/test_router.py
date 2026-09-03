"""HTTP-level tests for the password-reset endpoints.

Service behaviour is covered in tests/auth/test_service.py; here we exercise the
router: status codes, rate limits, enumeration parity, and the broker-outage
path. A throwaway FastAPI app is built with fakeredis and the repo dependencies
overridden by in-memory fakes.
"""

import time
from datetime import UTC, datetime, timedelta

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis_fastapi import FastAPIRedis
from redis_fastapi import deps as redis_fastapi_deps
from sqlalchemy.exc import IntegrityError

from backend.auth import router as auth_router_module
from backend.auth import service
from backend.auth.config import AuthConfig
from backend.auth.dependencies import (
    get_auth_config,
    get_email_verification_token_repo,
    get_password_reset_token_repo,
    get_pwned_password_checker,
    get_refresh_token_repo,
    get_user_repo,
)
from backend.auth.error_handlers import add_auth_error_handlers
from backend.auth.exceptions import InvalidCredentials, InvalidRefreshToken
from backend.mail.dependencies import get_email_outbox_repo
from tests.auth.fakes import (
    FakeEmailVerificationTokenRepository,
    FakePasswordResetTokenRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
)
from tests.mail.fakes import FakeEmailOutboxRepository

TEST_JWT_SECRET = "test-secret-1234567890123456789012345678901234567890123456789012"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
GOOD_PASSWORD = "a-fresh-long-passphrase"


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def reset_token_repo() -> FakePasswordResetTokenRepository:
    return FakePasswordResetTokenRepository()


@pytest.fixture
def refresh_token_repo() -> FakeRefreshTokenRepository:
    return FakeRefreshTokenRepository()


@pytest.fixture
def outbox_repo() -> FakeEmailOutboxRepository:
    return FakeEmailOutboxRepository()


@pytest.fixture
def register_response_floor() -> timedelta:
    """Padding applied to `POST /auth/register`; zeroed by default so tests stay fast.

    Override in a class to exercise the timing floor itself.
    """
    return timedelta(0)


@pytest.fixture
def app_config(register_response_floor) -> AuthConfig:
    return AuthConfig(
        JWT_SECRET=TEST_JWT_SECRET,
        PASSWORD_RESET_TOKEN_EXP=timedelta(hours=1),
        FORGOT_PASSWORD_RESPONSE_FLOOR=timedelta(0),
        AUTH_REGISTER_RESPONSE_FLOOR=register_response_floor,
    )


@pytest.fixture
def dispatch_calls() -> list[str]:
    return []


class FakePwnedChecker:
    def __init__(self) -> None:
        self.pwned: set[str] = set()
        self.calls: list[str] = []

    async def is_pwned(self, password: str) -> bool:
        self.calls.append(password)
        return password in self.pwned


@pytest.fixture
def pwned_checker() -> FakePwnedChecker:
    return FakePwnedChecker()


@pytest.fixture
async def verified_user(user_repo):
    user = await service.register_user(user_repo, email="ada@example.com", password="s3cret-pw")
    await user_repo.mark_email_verified(user.id, verified_at=NOW)
    return await user_repo.get_by_id(user.id)


@pytest.fixture
async def client(
    monkeypatch,
    user_repo,
    reset_token_repo,
    refresh_token_repo,
    outbox_repo,
    app_config,
    dispatch_calls,
    pwned_checker,
):
    fake_redis = fakeredis.aioredis.FakeRedis(server=fakeredis.aioredis.FakeServer())

    async def fake_get_async_redis(request):
        return fake_redis

    monkeypatch.setattr(redis_fastapi_deps, "get_async_redis", fake_get_async_redis)
    monkeypatch.setattr(auth_router_module.dispatch_email, "delay", dispatch_calls.append)

    app = FastAPI()
    FastAPIRedis(app).lifespan().rate_limiting()
    app.include_router(auth_router_module.router)
    add_auth_error_handlers(app)
    app.dependency_overrides.update(
        {
            get_auth_config: lambda: app_config,
            get_user_repo: lambda: user_repo,
            get_password_reset_token_repo: lambda: reset_token_repo,
            get_refresh_token_repo: lambda: refresh_token_repo,
            get_email_verification_token_repo: FakeEmailVerificationTokenRepository,
            get_email_outbox_repo: lambda: outbox_repo,
            get_pwned_password_checker: lambda: pwned_checker,
        }
    )

    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def _reset_token(client, outbox_repo) -> str:
    await client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    return next(iter(outbox_repo._entries_by_id.values())).token


class TestForgotPassword:
    async def test_known_verified_email_gets_204_and_queues_one_email(
        self, client, outbox_repo, dispatch_calls, verified_user
    ):
        res = await client.post("/auth/forgot-password", json={"email": "ada@example.com"})

        assert res.status_code == 204
        assert res.content == b""
        queued = list(outbox_repo._entries_by_id.values())
        assert len(queued) == 1
        assert queued[0].email == "ada@example.com"
        assert len(dispatch_calls) == 1

    async def test_unknown_email_gets_identical_204_and_queues_nothing(
        self, client, outbox_repo, dispatch_calls
    ):
        res = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

        assert res.status_code == 204
        assert res.content == b""
        assert list(outbox_repo._entries_by_id.values()) == []
        assert dispatch_calls == []

    async def test_unverified_email_gets_identical_204_and_queues_nothing(
        self, client, outbox_repo, user_repo
    ):
        await service.register_user(user_repo, email="grace@example.com", password="s3cret-pw")
        res = await client.post("/auth/forgot-password", json={"email": "grace@example.com"})

        assert res.status_code == 204
        assert res.content == b""
        assert list(outbox_repo._entries_by_id.values()) == []

    async def test_still_204_when_the_broker_is_down(
        self, client, monkeypatch, outbox_repo, verified_user
    ):
        def boom(entry_id):
            raise RuntimeError("broker unreachable")

        monkeypatch.setattr(auth_router_module.dispatch_email, "delay", boom)
        res = await client.post("/auth/forgot-password", json={"email": "ada@example.com"})

        assert res.status_code == 204
        assert len(list(outbox_repo._entries_by_id.values())) == 1

    async def test_malformed_body_is_422(self, client):
        res = await client.post("/auth/forgot-password", json={"email": "not-an-email"})

        assert res.status_code == 422


class TestResetPassword:
    async def test_happy_path_sets_new_password(
        self, client, outbox_repo, user_repo, verified_user
    ):
        token = await _reset_token(client, outbox_repo)
        res = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )

        assert res.status_code == 204
        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password=GOOD_PASSWORD
        )
        assert user.id == verified_user.id

    async def test_old_password_stops_working(self, client, outbox_repo, user_repo, verified_user):
        token = await _reset_token(client, outbox_repo)
        await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )

        with pytest.raises(InvalidCredentials):
            await service.authenticate_user(
                user_repo, email="ada@example.com", password="s3cret-pw"
            )

    async def test_pre_reset_refresh_token_is_revoked(
        self, client, outbox_repo, refresh_token_repo, app_config, verified_user
    ):
        session = await service.issue_token_pair(
            refresh_token_repo, verified_user, config=app_config, now=NOW
        )
        token = await _reset_token(client, outbox_repo)

        await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )

        with pytest.raises(InvalidRefreshToken):
            await service.rotate_refresh_token(
                refresh_token_repo, session.refresh_token, config=app_config, now=NOW
            )

    async def test_unknown_token_is_400(self, client, verified_user):
        res = await client.post(
            "/auth/reset-password", json={"token": "never-issued", "new_password": GOOD_PASSWORD}
        )

        assert res.status_code == 400
        assert res.json()["detail"] == "Invalid or expired reset token"

    async def test_replaying_a_used_token_is_400(self, client, outbox_repo, verified_user):
        token = await _reset_token(client, outbox_repo)
        await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )

        res = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": "another-good-one-42"}
        )

        assert res.status_code == 400

    async def test_expired_token_is_400_and_password_unchanged(
        self, client, outbox_repo, reset_token_repo, user_repo, verified_user
    ):
        token = await _reset_token(client, outbox_repo)
        next(iter(reset_token_repo._tokens_by_id.values())).expires_at = NOW - timedelta(days=1)

        res = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )

        assert res.status_code == 400
        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password="s3cret-pw"
        )
        assert user.id == verified_user.id


class TestAbuse:
    async def test_response_is_byte_identical_for_known_and_unknown(self, client, verified_user):
        known = await client.post("/auth/forgot-password", json={"email": "ada@example.com"})
        unknown = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})

        assert known.status_code == unknown.status_code == 204
        assert known.content == unknown.content == b""

    async def test_second_outstanding_token_dies_after_one_reset(
        self, client, outbox_repo, verified_user
    ):
        await client.post("/auth/forgot-password", json={"email": "ada@example.com"})
        first = next(iter(outbox_repo._entries_by_id.values())).token
        await client.post("/auth/forgot-password", json={"email": "ada@example.com"})
        second = next(t.token for t in outbox_repo._entries_by_id.values() if t.token != first)

        assert (
            await client.post(
                "/auth/reset-password", json={"token": second, "new_password": GOOD_PASSWORD}
            )
        ).status_code == 204

        stale = await client.post(
            "/auth/reset-password", json={"token": first, "new_password": "yet-another-one-42"}
        )
        assert stale.status_code == 400


class TestRegister:
    """`POST /auth/register` — enumeration-safe: 204 for any acceptable password,
    identical for a new and an already-registered address (Δ1, FR-036, SC-013)."""

    async def test_new_email_is_204_with_empty_body(self, client, user_repo):
        res = await client.post(
            "/auth/register", json={"email": "new@example.com", "password": GOOD_PASSWORD}
        )

        assert res.status_code == 204
        assert res.content == b""
        assert await user_repo.get_by_email("new@example.com") is not None

    async def test_new_email_queues_one_verification_email(
        self, client, outbox_repo, dispatch_calls
    ):
        await client.post(
            "/auth/register", json={"email": "new@example.com", "password": GOOD_PASSWORD}
        )

        queued = list(outbox_repo._entries_by_id.values())
        assert len(queued) == 1
        assert queued[0].email == "new@example.com"
        assert len(dispatch_calls) == 1

    async def test_email_is_normalized_before_storage(self, client, user_repo):
        res = await client.post(
            "/auth/register", json={"email": "  New@Example.com  ", "password": GOOD_PASSWORD}
        )

        assert res.status_code == 204
        assert await user_repo.get_by_email("new@example.com") is not None

    async def test_too_short_password_is_422(self, client):
        res = await client.post(
            "/auth/register", json={"email": "new@example.com", "password": "eightchr"}
        )

        assert res.status_code == 422
        assert "too short" in res.json()["detail"]

    async def test_breached_password_is_422(self, client, pwned_checker):
        pwned_checker.pwned.add("hunter2-hunter2-hunter2")

        res = await client.post(
            "/auth/register",
            json={"email": "new@example.com", "password": "hunter2-hunter2-hunter2"},
        )

        assert res.status_code == 422
        assert "data breach" in res.json()["detail"]


class TestRegisterEnumerationSafety:
    """An already-registered address must be indistinguishable from a fresh one."""

    async def test_existing_verified_email_gets_identical_204(
        self, client, verified_user, user_repo, outbox_repo, dispatch_calls
    ):
        new = await client.post(
            "/auth/register", json={"email": "fresh@example.com", "password": GOOD_PASSWORD}
        )
        outbox_repo._entries_by_id.clear()
        dispatch_calls.clear()

        existing = await client.post(
            "/auth/register", json={"email": "ada@example.com", "password": GOOD_PASSWORD}
        )

        assert existing.status_code == new.status_code == 204
        assert existing.content == new.content == b""
        # nothing about the response distinguishes the two — ignoring only the
        # request-ordinal rate-limit counters and the wall-clock Date header.
        volatile = {"date", "x-ratelimit-remaining", "x-ratelimit-reset"}
        assert {k: v for k, v in existing.headers.items() if k not in volatile} == {
            k: v for k, v in new.headers.items() if k not in volatile
        }
        assert "set-cookie" not in existing.headers

    async def test_existing_verified_email_creates_no_row_and_sends_no_email(
        self, client, verified_user, user_repo, outbox_repo, dispatch_calls
    ):
        res = await client.post(
            "/auth/register", json={"email": "ada@example.com", "password": "a-brand-new-long-pw"}
        )

        assert res.status_code == 204
        # still exactly one user for that address, and its password is untouched
        assert await service.authenticate_user(
            user_repo, email="ada@example.com", password="s3cret-pw"
        )
        assert list(outbox_repo._entries_by_id.values()) == []
        assert dispatch_calls == []

    async def test_existing_unverified_email_is_a_silent_204_no_op(
        self, client, user_repo, outbox_repo
    ):
        await service.register_user(
            user_repo, email="grace@example.com", password="s3cret-pw"
        )

        res = await client.post(
            "/auth/register", json={"email": "grace@example.com", "password": GOOD_PASSWORD}
        )

        assert res.status_code == 204
        assert list(outbox_repo._entries_by_id.values()) == []

    async def test_breached_password_422_is_identical_for_new_and_existing_email(
        self, client, verified_user, pwned_checker
    ):
        pwned_checker.pwned.add("hunter2-hunter2-hunter2")

        unknown = await client.post(
            "/auth/register",
            json={"email": "nobody@example.com", "password": "hunter2-hunter2-hunter2"},
        )
        existing = await client.post(
            "/auth/register",
            json={"email": "ada@example.com", "password": "hunter2-hunter2-hunter2"},
        )

        assert unknown.status_code == existing.status_code == 422
        assert unknown.json() == existing.json()

    async def test_a_create_race_resolves_as_204_not_500(
        self, client, user_repo, monkeypatch
    ):
        """Email inserted between the pre-check and our insert (R5)."""

        async def racing_create(*, email: str, password_hash: str):
            raise IntegrityError("INSERT INTO users", {}, Exception("duplicate key: email"))

        monkeypatch.setattr(user_repo, "create", racing_create)

        res = await client.post(
            "/auth/register", json={"email": "racer@example.com", "password": GOOD_PASSWORD}
        )

        assert res.status_code == 204
        assert res.content == b""


class TestRegisterResponseFloor:
    """Both the new-email and existing-email paths are padded to the floor (R2)."""

    @pytest.fixture
    def register_response_floor(self) -> timedelta:
        return timedelta(milliseconds=200)

    async def test_new_email_response_is_padded_to_the_floor(self, client):
        start = time.perf_counter()
        res = await client.post(
            "/auth/register", json={"email": "slow@example.com", "password": GOOD_PASSWORD}
        )
        elapsed = time.perf_counter() - start

        assert res.status_code == 204
        assert elapsed >= 0.2

    async def test_existing_email_response_is_padded_to_the_floor(self, client, verified_user):
        start = time.perf_counter()
        res = await client.post(
            "/auth/register", json={"email": "ada@example.com", "password": GOOD_PASSWORD}
        )
        elapsed = time.perf_counter() - start

        assert res.status_code == 204
        assert elapsed >= 0.2


class TestPasswordPolicyAtReset:
    async def test_policy_violation_is_422_and_the_token_stays_usable(
        self, client, outbox_repo, user_repo, verified_user
    ):
        token = await _reset_token(client, outbox_repo)
        rejected = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": "ninechars"}
        )
        assert rejected.status_code == 422
        assert "too short" in rejected.json()["detail"]

        accepted = await client.post(
            "/auth/reset-password", json={"token": token, "new_password": GOOD_PASSWORD}
        )
        assert accepted.status_code == 204
        user = await service.authenticate_user(
            user_repo, email="ada@example.com", password=GOOD_PASSWORD
        )
        assert user.id == verified_user.id

    async def test_unknown_token_with_a_policy_violating_password_is_400_not_422(
        self, client, verified_user
    ):
        res = await client.post(
            "/auth/reset-password", json={"token": "never-issued", "new_password": "ninechars"}
        )

        assert res.status_code == 400
