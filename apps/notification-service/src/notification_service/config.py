"""Runtime configuration for notification service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "notification-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    metrics_enabled: bool = True

    event_produced_by: str = "apps/notification-service"
    max_retry_attempts: int = 3
    fallback_channels: tuple[str, ...] = ("chat", "webhook", "email", "sms")

    model_config = SettingsConfigDict(env_prefix="NOTIFICATION_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
