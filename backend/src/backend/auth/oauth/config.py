from datetime import timedelta
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class OAuthConfig(BaseSettings):
    """Provider-agnostic sign-in knobs, read from the flat `.env` namespace.

    `OAUTH_ENABLED_PROVIDERS` is a comma-separated list of module names under
    `providers/`; empty runs the app with password sign-in only. Each adapter
    declares its own settings in its own module, so nothing provider-specific
    belongs here. No `env_prefix`, as in `AuthConfig`.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    OAUTH_ENABLED_PROVIDERS: Annotated[list[str], NoDecode] = []
    OAUTH_STATE_TTL: timedelta = timedelta(minutes=10)
    OAUTH_LINK_TOKEN_EXP: timedelta = timedelta(hours=1)

    @field_validator("OAUTH_ENABLED_PROVIDERS", mode="before")
    @classmethod
    def _split_providers(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]


oauth_settings = OAuthConfig()
