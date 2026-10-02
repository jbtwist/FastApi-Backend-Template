from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: PostgresDsn
    DB_POOL_SIZE: int = Field(default=5, ge=1)
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0)
    DB_POOL_TIMEOUT: float = Field(default=3.0, gt=0)
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:8081"
    CORS_ALLOWED_ORIGINS: Annotated[list[str], NoDecode] = ["http://localhost:8081"]
    RATE_LIMIT_ENABLED: bool = True
    REDIS_URL: str = "redis://localhost:6379"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "console"

    @field_validator("CORS_ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("CORS_ALLOWED_ORIGINS", mode="after")
    @classmethod
    def _check_origins(cls, origins: list[str]) -> list[str]:
        """An `Origin` header is scheme://host[:port], so a trailing slash never matches."""
        origins = [origin.rstrip("/") for origin in origins]
        if "*" in origins:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS cannot be '*': the API is called with credentials, "
                "so every origin has to be listed explicitly"
            )
        return origins


settings = Settings()
