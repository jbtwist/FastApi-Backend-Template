from typing import Annotated

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: PostgresDsn
    # Browser origins allowed to call this API. Comma-separated in the
    # environment; each deployment (dev, acceptance, production) sets its own,
    # and the default only covers the local Expo web dev server.
    # `NoDecode` keeps pydantic-settings from JSON-parsing the raw value so the
    # validator below can split it.
    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:8081"]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="after")
    @classmethod
    def _check_origins(cls, origins: list[str]) -> list[str]:
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS cannot be '*': the API is called with credentials, "
                "so every origin has to be listed explicitly"
            )
        # An `Origin` header is scheme://host[:port] — a trailing slash would
        # never match, silently.
        return [origin.rstrip("/") for origin in origins]


settings = Settings()
