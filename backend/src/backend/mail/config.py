from pydantic_settings import BaseSettings, SettingsConfigDict


class MailConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MAIL_", env_file=".env", extra="ignore")

    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    MAX_DISPATCH_ATTEMPTS: int = 5


mail_settings = MailConfig()
