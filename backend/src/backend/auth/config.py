from datetime import timedelta
from enum import StrEnum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PasswordStrength(StrEnum):
    """Minimum-length tier for accepted passwords.

    Floors live in `backend.auth.password_policy.MIN_LENGTH_BY_STRENGTH`, each
    tier tracking a published one:

    - `LOW` = 8 — below every single-factor recommendation, and the shortest
      [NIST SP 800-63B-4 §3.1.1.2][nist] allows at all, which it permits only
      for a password used *inside* multi-factor authentication.
    - `MEDIUM` = 12 — the [ASVS v4 2.1.1][asvs] baseline. The default.
    - `HIGH` = 15 — the [NIST SP 800-63B-4][nist] minimum for a password used as
      a single factor, which is what this app does.

    [asvs]: https://github.com/OWASP/ASVS/blob/v4.0.3/4.0/en/0x11-V2-Authentication.md
    [nist]: https://pages.nist.gov/800-63-4/sp800-63b.html
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AuthConfig(BaseSettings):
    """Auth knobs, read from the flat `.env` namespace.

    Deliberately no `env_prefix`: settings are split into classes for code
    locality, but the `.env` file is one global namespace, so a field's name is
    its environment variable name. Field names must therefore be unique across
    `AuthConfig`, `MailConfig` and `backend.config.Settings`, and self-describing
    on their own — nothing scopes them at read time.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_EXP: timedelta = timedelta(minutes=15)
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)
    EMAIL_VERIFICATION_TOKEN_EXP: timedelta = timedelta(hours=24)
    PASSWORD_RESET_TOKEN_EXP: timedelta = timedelta(hours=1)
    FORGOT_PASSWORD_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    REGISTER_RESPONSE_FLOOR: timedelta = timedelta(milliseconds=500)
    PASSWORD_STRENGTH: PasswordStrength = PasswordStrength.MEDIUM
    PASSWORD_MAX_LENGTH: int = Field(default=128, ge=64)
    PASSWORD_CHECK_PWNED: bool = True
    COOKIE_SECURE: bool = True
    RATE_LIMIT_ENABLED: bool = True


auth_settings = AuthConfig()
