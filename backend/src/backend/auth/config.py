from datetime import timedelta

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXP: timedelta = timedelta(minutes=15)
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)
    EMAIL_VERIFICATION_TOKEN_EXP: timedelta = timedelta(hours=24)
    COOKIE_SECURE: bool = True


auth_settings = AuthConfig()
