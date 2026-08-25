from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class MailConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAIL_", env_file=".env", extra="ignore")
    # Celery settings
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    # SMTP settings
    PROVIDER: Literal["ses", "smtp"] = "smtp"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    FROM_EMAIL: str
    # Public base URL of this API, used to build the confirm-email link
    API_BASE_URL: str = "http://localhost:8000"
    # Email dispatch settings
    MAX_DISPATCH_ATTEMPTS: int = 5
    SWEEP_INTERVAL_SECONDS: int = 60
    SWEEP_STALE_AFTER_SECONDS: int = 120
    # AWS settings
    AWS_REGION: str = "eu-west-1"


mail_settings = MailConfig()
