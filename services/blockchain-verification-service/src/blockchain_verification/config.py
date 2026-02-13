"""Runtime configuration for blockchain verification service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "blockchain-verification-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    metrics_enabled: bool = True

    event_produced_by: str = "services/blockchain-verification-service"
    required_confirmations: int = 3
    initial_block_number: int = 100000

    model_config = SettingsConfigDict(env_prefix="BLOCKCHAIN_VERIFICATION_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
