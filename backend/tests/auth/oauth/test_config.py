from datetime import timedelta

import pytest

from backend.auth.oauth.config import OAuthConfig


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("google,apple", ["google", "apple"]),
        (" google , apple ", ["google", "apple"]),
        ("google,,", ["google"]),
        ("", []),
    ],
)
def test_enabled_providers_parse_from_a_comma_separated_variable(monkeypatch, raw, expected):
    monkeypatch.setenv("OAUTH_ENABLED_PROVIDERS", raw)

    assert OAuthConfig(_env_file=None).OAUTH_ENABLED_PROVIDERS == expected


def test_defaults_enable_no_provider_and_a_ten_minute_state(monkeypatch):
    monkeypatch.delenv("OAUTH_ENABLED_PROVIDERS", raising=False)
    monkeypatch.delenv("OAUTH_STATE_TTL", raising=False)

    config = OAuthConfig(_env_file=None)

    assert config.OAUTH_ENABLED_PROVIDERS == []
    assert config.OAUTH_STATE_TTL == timedelta(seconds=600)
