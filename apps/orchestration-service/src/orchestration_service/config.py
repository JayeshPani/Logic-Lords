"""Runtime configuration for orchestration service."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "orchestration-service"
    service_version: str = "0.1.0"
    log_level: str = "INFO"
    metrics_enabled: bool = True

    event_produced_by: str = "apps/orchestration-service"
    command_requested_by: str = "agents/openclaw-agent"
    workflow_name: str = "high-risk-detection"

    trigger_risk_levels: tuple[str, ...] = ("High", "Critical")
    min_health_score: float = 0.70
    min_failure_probability: float = 0.60
    max_retry_attempts: int = 3

    model_config = SettingsConfigDict(env_prefix="ORCHESTRATION_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
