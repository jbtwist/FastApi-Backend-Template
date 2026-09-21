from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class MailConfig(BaseSettings):
    """Mail knobs, read from the flat `.env` namespace.

    Deliberately no `env_prefix` — see `backend.auth.config.AuthConfig` for the
    convention. Fields that would be ambiguous on their own carry `EMAIL_` as
    part of their name rather than as a namespace.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Celery settings
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    # SMTP settings
    EMAIL_PROVIDER: Literal["ses", "smtp"] = "smtp"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    FROM_EMAIL: str
    # Email dispatch settings
    EMAIL_MAX_DISPATCH_ATTEMPTS: int = 5
    EMAIL_SWEEP_INTERVAL_SECONDS: int = 60
    EMAIL_SWEEP_STALE_AFTER_SECONDS: int = 120
    # AWS settings
    AWS_REGION: str = "eu-west-1"


mail_settings = MailConfig()
