"""Runtime configuration for report generation service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "report-generation-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    metrics_enabled: bool = True

    event_produced_by: str = "services/report-generation-service"
    command_requested_by: str = "services/report-generation-service"
    blockchain_network: str = "sepolia"
    blockchain_contract_address: str = "0x1111111111111111111111111111111111111111"
    blockchain_chain_id: int = 11155111

    model_config = SettingsConfigDict(env_prefix="REPORT_GENERATION_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
