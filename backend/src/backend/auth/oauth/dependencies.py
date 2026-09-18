from functools import cache
from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from backend.auth.oauth.config import OAuthConfig, oauth_settings
from backend.auth.oauth.contract import OAuthProvider
from backend.auth.oauth.exceptions import ProviderNotConfigured
from backend.auth.oauth.registry import enabled_providers
from backend.auth.oauth.repository import SqlOAuthIdentityRepository, SqlOAuthLinkTokenRepository
from backend.auth.oauth.state import RedisSignInStateStore
from backend.config import settings
from backend.database import DbDep


def get_oauth_config() -> OAuthConfig:
    return oauth_settings


@cache
def get_enabled_providers() -> dict[str, OAuthProvider]:
    """Every provider this deployment offers, loaded once per process."""
    return enabled_providers(oauth_settings)


def get_provider(
    provider: str,
    providers: Annotated[dict[str, OAuthProvider], Depends(get_enabled_providers)],
) -> OAuthProvider:
    """The adapter named by the `{provider}` path segment.

    The name is only ever looked up among the loaded providers, never imported.

    Raises:
        ProviderNotConfigured: the deployment doesn't offer that provider.
    """
    try:
        return providers[provider]
    except KeyError:
        raise ProviderNotConfigured(provider) from None


@cache
def _redis() -> Redis:
    return Redis.from_url(settings.REDIS_URL)


def get_state_store() -> RedisSignInStateStore:
    return RedisSignInStateStore(_redis())


def get_identity_repo(db: DbDep) -> SqlOAuthIdentityRepository:
    return SqlOAuthIdentityRepository(db)


def get_link_token_repo(db: DbDep) -> SqlOAuthLinkTokenRepository:
    return SqlOAuthLinkTokenRepository(db)


OAuthConfigDep = Annotated[OAuthConfig, Depends(get_oauth_config)]
EnabledProvidersDep = Annotated[dict[str, OAuthProvider], Depends(get_enabled_providers)]
ProviderDep = Annotated[OAuthProvider, Depends(get_provider)]
StateStoreDep = Annotated[RedisSignInStateStore, Depends(get_state_store)]
OAuthIdentityRepoDep = Annotated[SqlOAuthIdentityRepository, Depends(get_identity_repo)]
OAuthLinkTokenRepoDep = Annotated[SqlOAuthLinkTokenRepository, Depends(get_link_token_repo)]
