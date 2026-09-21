"""Resolve provider names to adapters by discovery, so adding one edits no shared file."""

import importlib
import logging

from pydantic import ValidationError

from backend.auth.oauth.config import OAuthConfig
from backend.auth.oauth.contract import OAuthProvider
from backend.auth.oauth.exceptions import ProviderNotConfigured

logger = logging.getLogger(__name__)


def load_provider(name: str) -> OAuthProvider:
    """Resolve a provider name to its adapter at `providers/<name>.py`.

    `name` is interpolated into an import path, so it must come from
    configuration, never from a request; see `enabled_providers`.

    Raises:
        ProviderNotConfigured: no such module, no `PROVIDER`, or incomplete
            configuration.
    """
    try:
        module = importlib.import_module(f"backend.auth.oauth.providers.{name}")
        return module.PROVIDER
    except (ImportError, AttributeError, ValidationError) as exc:
        raise ProviderNotConfigured(name) from exc


def enabled_providers(config: OAuthConfig) -> dict[str, OAuthProvider]:
    """Load every provider named in `OAUTH_ENABLED_PROVIDERS`, keyed by name, in that order.

    A provider that fails to load, for any reason, is left out while the rest
    still load, so one broken adapter can't stop the app starting. The failure is
    logged by name and exception type only: a settings error's message can carry
    configured values, secrets included.
    """
    loaded: dict[str, OAuthProvider] = {}
    for name in config.OAUTH_ENABLED_PROVIDERS:
        try:
            loaded[name] = load_provider(name)
        except Exception as exc:
            cause = exc.__cause__ or exc
            logger.warning("OAuth provider %r not loaded: %s", name, type(cause).__name__)
    return loaded
