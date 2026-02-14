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
    firebase_storage_bucket: str = ""
    firebase_project_id: str | None = None
    firebase_credentials_json: str = ""
    evidence_upload_url_ttl_seconds: int = 900
    evidence_max_file_bytes: int = 20 * 1024 * 1024
    evidence_allowed_mime_types_csv: str = "application/pdf,image/jpeg,image/png,image/webp,video/mp4"

    model_config = SettingsConfigDict(env_prefix="REPORT_GENERATION_", extra="ignore")

    @property
    def evidence_allowed_mime_types(self) -> tuple[str, ...]:
        values = [value.strip().lower() for value in self.evidence_allowed_mime_types_csv.split(",")]
        unique: list[str] = []
        for value in values:
            if value and value not in unique:
                unique.append(value)
        return tuple(unique)


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
