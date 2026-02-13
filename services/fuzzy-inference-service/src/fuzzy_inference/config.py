"""Runtime configuration for fuzzy inference."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "fuzzy-inference-service"
    service_version: str = "0.2.0"

    centroid_resolution: int = 401

    model_config = SettingsConfigDict(env_prefix="FUZZY_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
