from datetime import timedelta
from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PasswordStrength(StrEnum):
    """Minimum-length tier for accepted passwords.

    Floors live in `backend.auth.password_policy.MIN_LENGTH_BY_STRENGTH`:
    LOW = 8 (ASVS/NIST absolute minimum), MEDIUM = 12 (ASVS v4 2.1.1 baseline),
    HIGH = 15 (NIST SP 800-63B recommended).
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXP: timedelta = timedelta(minutes=15)
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)
    EMAIL_VERIFICATION_TOKEN_EXP: timedelta = timedelta(hours=24)
    PASSWORD_RESET_TOKEN_EXP: timedelta = timedelta(hours=1)
    FORGOT_PASSWORD_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    AUTH_REGISTER_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    PASSWORD_STRENGTH: PasswordStrength = PasswordStrength.MEDIUM
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=64)
    PASSWORD_CHECK_PWNED: bool = True
    COOKIE_SECURE: bool = True


auth_settings = AuthConfig()
