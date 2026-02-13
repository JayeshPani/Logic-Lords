"""Runtime configuration for fuzzy inference."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "fuzzy-inference-service"
    service_version: str = "0.3.0"

    centroid_resolution: int = 401
    log_level: str = "INFO"
    metrics_enabled: bool = True
    anomaly_flag_threshold: float = Field(default=0.7, ge=0, le=1)
    event_produced_by: str = "services/fuzzy-inference-service"

    model_config = SettingsConfigDict(env_prefix="FUZZY_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
