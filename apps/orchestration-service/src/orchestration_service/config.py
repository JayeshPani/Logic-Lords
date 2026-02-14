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
    authority_ack_sla_minutes: int = 30
    escalation_check_interval_seconds: int = 30
    notification_base_url: str = "http://127.0.0.1:8201"
    notification_timeout_seconds: float = 8.0
    management_recipients_csv: str = "management@infraguard.local"
    management_channels_csv: str = "email,sms,webhook"
    police_recipients_csv: str = "police-control@infraguard.local"
    police_channels_csv: str = "webhook,sms"
    report_generation_base_url: str = "http://127.0.0.1:8202"
    report_generation_timeout_seconds: float = 8.0
    blockchain_verification_base_url: str = "http://127.0.0.1:8105"
    blockchain_verification_timeout_seconds: float = 8.0

    model_config = SettingsConfigDict(env_prefix="ORCHESTRATION_", extra="ignore")

    @property
    def management_recipients(self) -> tuple[str, ...]:
        values = [value.strip() for value in self.management_recipients_csv.split(",")]
        return tuple(value for value in values if value)

    @property
    def management_channels(self) -> tuple[str, ...]:
        values = [value.strip().lower() for value in self.management_channels_csv.split(",")]
        unique: list[str] = []
        for value in values:
            if value and value not in unique:
                unique.append(value)
        return tuple(unique)

    @property
    def police_recipients(self) -> tuple[str, ...]:
        values = [value.strip() for value in self.police_recipients_csv.split(",")]
        return tuple(value for value in values if value)

    @property
    def police_channels(self) -> tuple[str, ...]:
        values = [value.strip().lower() for value in self.police_channels_csv.split(",")]
        unique: list[str] = []
        for value in values:
            if value and value not in unique:
                unique.append(value)
        return tuple(unique)


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
