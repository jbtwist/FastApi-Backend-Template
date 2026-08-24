from pydantic_settings import BaseSettings, SettingsConfigDict


class MailConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAIL_", env_file=".env", extra="ignore")

    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str
    MAX_DISPATCH_ATTEMPTS: int = 5
    SWEEP_INTERVAL_SECONDS: int = 60
    SWEEP_STALE_AFTER_SECONDS: int = 120


mail_settings = MailConfig()
