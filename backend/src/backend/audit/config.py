"""Audit settings, read from the same flat env namespace as every other config class."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuditConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECURITY_EVENT_RETENTION_DAYS: int = 180
    SECURITY_EVENT_SWEEP_INTERVAL_SECONDS: int = 86400
    SECURITY_EVENT_PURGE_BATCH_SIZE: int = 5000


audit_settings = AuditConfig()
