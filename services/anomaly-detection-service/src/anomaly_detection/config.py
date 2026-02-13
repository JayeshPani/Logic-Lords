"""Runtime configuration for anomaly detection."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "anomaly-detection-service"
    service_version: str = "0.2.0"

    n_estimators: int = 100
    contamination: float = Field(default=0.02, ge=0.0, le=0.5)
    random_state: int = 42

    min_baseline_points: int = 16
    anomaly_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    pretrained_model_path: str | None = "data-platform/ml/models/isolation_forest.joblib"
    pretrained_meta_path: str | None = "data-platform/ml/models/isolation_forest.meta.json"
    fallback_to_heuristic_on_startup_error: bool = True
    min_model_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    log_level: str = "INFO"
    metrics_enabled: bool = True
    event_produced_by: str = "services/anomaly-detection-service"

    model_config = SettingsConfigDict(env_prefix="ANOMALY_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
