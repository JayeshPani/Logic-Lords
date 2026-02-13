"""Application configuration settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    service_name: str = "asset-registry-service"
    service_version: str = "0.1.0"
    database_url: str = "sqlite:///./asset_registry.db"
    sql_echo: bool = False

    model_config = SettingsConfigDict(env_prefix="ASSET_REGISTRY_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
