from datetime import timedelta
from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PasswordStrength(StrEnum):
    """Minimum-length tier, floors in `password_policy.MIN_LENGTH_BY_STRENGTH`.

    8 is the [NIST][nist] floor for a password used inside MFA, 12 the
    [ASVS v4 2.1.1][asvs] baseline, 15 the [NIST][nist] minimum for a single
    factor, which is what this app does.

    [asvs]: https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x11-V2-Authentication.md
    [nist]: https://pages.nist.gov/800-63-4/sp800-63b.html
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuthConfig(BaseSettings):
    """Auth knobs, read from the flat `.env` namespace.

    No `env_prefix`: a field's name is its environment variable name, so names
    must be unique across `AuthConfig`, `MailConfig` and `backend.config.Settings`.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXP: timedelta = timedelta(minutes=15)
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)
    REFRESH_TOKEN_REUSE_GRACE: timedelta = timedelta(seconds=10)
    EMAIL_VERIFICATION_TOKEN_EXP: timedelta = timedelta(hours=24)
    PASSWORD_RESET_TOKEN_EXP: timedelta = timedelta(hours=1)
    FORGOT_PASSWORD_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    REGISTER_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    PASSWORD_STRENGTH: PasswordStrength = PasswordStrength.MEDIUM
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=64)
    PASSWORD_CHECK_PWNED: bool = True
    COOKIE_SECURE: bool = True


auth_settings = AuthConfig()
