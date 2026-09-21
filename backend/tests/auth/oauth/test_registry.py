import importlib
import logging
import sys
import textwrap

import pytest

from backend.auth.oauth import providers
from backend.auth.oauth.config import OAuthConfig
from backend.auth.oauth.exceptions import ProviderNotConfigured
from backend.auth.oauth.registry import enabled_providers, load_provider

FAKE = """
    from tests.auth.oauth.fakes import FakeOAuthProvider

    PROVIDER = FakeOAuthProvider()
"""

SECOND_FAKE = """
    from tests.auth.oauth.fakes import SecondFakeOAuthProvider

    PROVIDER = SecondFakeOAuthProvider()
"""

NO_EXPORT = """
    from tests.auth.oauth.fakes import FakeOAuthProvider

    provider = FakeOAuthProvider()
"""

HALF_CONFIGURED = """
    from pydantic_settings import BaseSettings

    from tests.auth.oauth.fakes import FakeOAuthProvider


    class HalfConfig(BaseSettings):
        OAUTH_TEST_CLIENT_ID: str
        OAUTH_TEST_CLIENT_SECRET: str


    _config = HalfConfig()
    PROVIDER = FakeOAuthProvider()
"""

EXPLODES = """
    raise RuntimeError("adapter failed during construction")
"""

CLIENT_SECRET = "oauth-test-client-secret-value"


@pytest.fixture
def provider_modules(tmp_path, monkeypatch):
    """Adds adapter modules to `backend.auth.oauth.providers` from a throwaway directory.

    Each is one file named after its provider, exactly how a real adapter is added,
    and is evicted from the import system afterwards so no test sees another's.
    """
    monkeypatch.setattr(providers, "__path__", [*providers.__path__, str(tmp_path)])
    written: list[str] = []

    def write(name: str, source: str) -> None:
        (tmp_path / f"{name}.py").write_text(textwrap.dedent(source))
        importlib.invalidate_caches()
        written.append(name)

    yield write

    for name in written:
        sys.modules.pop(f"{providers.__name__}.{name}", None)
        vars(providers).pop(name, None)


@pytest.fixture
def half_configured_env(monkeypatch):
    """One setting present (a secret), one missing: a partly filled `.env`."""
    monkeypatch.setenv("OAUTH_TEST_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.delenv("OAUTH_TEST_CLIENT_ID", raising=False)


def _config(*names: str) -> OAuthConfig:
    return OAuthConfig(OAUTH_ENABLED_PROVIDERS=list(names), _env_file=None)


class TestLoadProvider:
    def test_resolves_a_name_to_its_modules_provider(self, provider_modules):
        provider_modules("fake", FAKE)

        provider = load_provider("fake")

        assert provider is sys.modules[f"{providers.__name__}.fake"].PROVIDER
        assert provider.name == "fake"

    def test_resolves_each_name_to_its_own_module(self, provider_modules):
        provider_modules("fake", FAKE)
        provider_modules("second_fake", SECOND_FAKE)

        assert load_provider("fake").name == "fake"
        assert load_provider("second_fake").name == "second_fake"

    def test_raises_not_configured_for_a_missing_module(self):
        with pytest.raises(ProviderNotConfigured):
            load_provider("absent")

    def test_raises_not_configured_when_the_module_exports_no_provider(self, provider_modules):
        provider_modules("no_export", NO_EXPORT)

        with pytest.raises(ProviderNotConfigured):
            load_provider("no_export")

    def test_raises_not_configured_when_settings_are_incomplete(
        self, provider_modules, half_configured_env
    ):
        provider_modules("half_configured", HALF_CONFIGURED)

        with pytest.raises(ProviderNotConfigured):
            load_provider("half_configured")


class TestEnabledProviders:
    def test_loads_every_enabled_provider_in_configured_order(self, provider_modules):
        provider_modules("fake", FAKE)
        provider_modules("second_fake", SECOND_FAKE)

        loaded = enabled_providers(_config("second_fake", "fake"))

        assert list(loaded) == ["second_fake", "fake"]
        assert loaded["fake"] is load_provider("fake")

    def test_nothing_enabled_loads_nothing(self):
        assert enabled_providers(_config()) == {}

    def test_a_provider_that_is_not_enabled_is_never_imported(self, provider_modules):
        provider_modules("fake", FAKE)
        provider_modules("second_fake", SECOND_FAKE)

        enabled_providers(_config("fake"))

        assert f"{providers.__name__}.second_fake" not in sys.modules

    def test_a_provider_that_fails_to_load_is_skipped_without_affecting_the_others(
        self, provider_modules, half_configured_env
    ):
        provider_modules("fake", FAKE)
        provider_modules("half_configured", HALF_CONFIGURED)
        provider_modules("explodes", EXPLODES)
        provider_modules("second_fake", SECOND_FAKE)

        loaded = enabled_providers(
            _config("fake", "half_configured", "absent", "explodes", "second_fake")
        )

        assert list(loaded) == ["fake", "second_fake"]

    def test_a_skipped_provider_never_echoes_its_settings(
        self, provider_modules, half_configured_env, caplog
    ):
        provider_modules("half_configured", HALF_CONFIGURED)

        with pytest.raises(ProviderNotConfigured) as exc_info:
            load_provider("half_configured")
        with caplog.at_level(logging.DEBUG):
            enabled_providers(_config("half_configured"))

        assert CLIENT_SECRET not in str(exc_info.value)
        assert CLIENT_SECRET not in caplog.text
