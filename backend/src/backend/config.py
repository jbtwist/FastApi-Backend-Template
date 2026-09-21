from typing import Annotated

from pydantic import PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: PostgresDsn
    # Where each half of the app is reachable. Both are public URLs that end up
    # in links and redirects: the API's own callback URLs, and every link this
    # app sends someone to (emails, the return leg of a provider sign-in).
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:8081"
    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:8081"]
    RATE_LIMIT_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379"

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
