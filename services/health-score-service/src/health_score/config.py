"""Runtime configuration for health score output service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "health-score-service"
    service_version: str = "0.2.0"

    model_config = SettingsConfigDict(env_prefix="HEALTH_SCORE_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
