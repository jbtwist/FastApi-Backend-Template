from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class MailConfig(BaseSettings):
    """Mail knobs, read from the flat `.env` namespace.

    No `env_prefix`, as in `AuthConfig`, so a field that would be ambiguous on
    its own carries `EMAIL_` in its name rather than as a namespace.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    EMAIL_PROVIDER: Literal["ses", "smtp"] = "smtp"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    FROM_EMAIL: str
    AWS_REGION: str = "eu-west-1"

    EMAIL_MAX_DISPATCH_ATTEMPTS: int = 5
    EMAIL_SWEEP_INTERVAL_SECONDS: int = 60
    EMAIL_SWEEP_STALE_AFTER_SECONDS: int = 120
    EMAIL_SWEEP_RETRYING_STALE_AFTER_SECONDS: int = 1200
    EMAIL_SWEEP_SENDING_STALE_AFTER_SECONDS: int = 300


mail_settings = MailConfig()
