import uuid
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from backend.auth import security
from backend.auth.dependencies import get_current_user
from tests.auth.fakes import FakeUserRepository


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def user_repo() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
async def registered_user(user_repo: FakeUserRepository):
    return await user_repo.create(email="user@example.com", password_hash="hash")


def _token_for(user_id: uuid.UUID, *, auth_config, now: datetime) -> str:
    return security.create_access_token(str(user_id), config=auth_config, now=now)


class TestGetCurrentUser:
    async def test_resolves_user_from_header_when_no_cookie(
        self, user_repo, registered_user, auth_config
    ):
        now = datetime.now(UTC)
        token = _token_for(registered_user.id, auth_config=auth_config, now=now)

        user = await get_current_user(
            user_repo, auth_config, credentials=_bearer(token), access_token=None
        )

        assert user.id == registered_user.id

    async def test_resolves_user_from_cookie_when_no_header(
        self, user_repo, registered_user, auth_config
    ):
        now = datetime.now(UTC)
        token = _token_for(registered_user.id, auth_config=auth_config, now=now)

        user = await get_current_user(user_repo, auth_config, credentials=None, access_token=token)

        assert user.id == registered_user.id

    async def test_header_wins_over_cookie_when_both_present(self, user_repo, auth_config):
        now = datetime.now(UTC)
        header_user = await user_repo.create(email="header@example.com", password_hash="hash")
        cookie_user = await user_repo.create(email="cookie@example.com", password_hash="hash")
        header_token = _token_for(header_user.id, auth_config=auth_config, now=now)
        cookie_token = _token_for(cookie_user.id, auth_config=auth_config, now=now)

        user = await get_current_user(
            user_repo,
            auth_config,
            credentials=_bearer(header_token),
            access_token=cookie_token,
        )

        assert user.id == header_user.id

    async def test_invalid_header_raises_even_with_valid_cookie(
        self, user_repo, registered_user, auth_config
    ):
        now = datetime.now(UTC)
        valid_cookie_token = _token_for(registered_user.id, auth_config=auth_config, now=now)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                user_repo,
                auth_config,
                credentials=_bearer("not-a-jwt-at-all"),
                access_token=valid_cookie_token,
            )

        assert exc_info.value.status_code == 401

    async def test_raises_when_neither_header_nor_cookie_present(self, user_repo, auth_config):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(user_repo, auth_config, credentials=None, access_token=None)

        assert exc_info.value.status_code == 401

    async def test_raises_when_header_token_valid_but_user_unknown(self, user_repo, auth_config):
        now = datetime.now(UTC)
        token = _token_for(uuid.uuid4(), auth_config=auth_config, now=now)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                user_repo, auth_config, credentials=_bearer(token), access_token=None
            )

        assert exc_info.value.status_code == 401
