from datetime import timedelta

import pytest

from backend.auth.oauth.config import OAuthConfig
from tests.auth.oauth.fakes import (
    FakeOAuthIdentityRepository,
    FakeOAuthLinkTokenRepository,
    FakeSignInStateStore,
)


@pytest.fixture
def oauth_config() -> OAuthConfig:
    return OAuthConfig(
        _env_file=None,
        OAUTH_ENABLED_PROVIDERS=["fake"],
        OAUTH_STATE_TTL=timedelta(minutes=10),
        OAUTH_LINK_TOKEN_EXP=timedelta(hours=1),
    )


@pytest.fixture
def identity_repo() -> FakeOAuthIdentityRepository:
    return FakeOAuthIdentityRepository()


@pytest.fixture
def link_token_repo() -> FakeOAuthLinkTokenRepository:
    return FakeOAuthLinkTokenRepository()


@pytest.fixture
def state_store() -> FakeSignInStateStore:
    return FakeSignInStateStore()
