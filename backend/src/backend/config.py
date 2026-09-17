from typing import Annotated

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: PostgresDsn
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
        # An `Origin` header is scheme://host[:port] — a trailing slash would
        # never match, silently.
        origins = [origin.rstrip("/") for origin in origins]
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS cannot be '*': the API is called with credentials, "
                "so every origin has to be listed explicitly"
            )
        return origins


settings = Settings()
