"""Runtime configuration for anomaly detection."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "anomaly-detection-service"
    service_version: str = "0.1.0"

    n_estimators: int = 100
    contamination: float = 0.02
    random_state: int = 42

    min_baseline_points: int = 16
    anomaly_threshold: float = 0.65
    pretrained_model_path: str | None = "data-platform/ml/models/isolation_forest.joblib"
    pretrained_meta_path: str | None = "data-platform/ml/models/isolation_forest.meta.json"

    model_config = SettingsConfigDict(env_prefix="ANOMALY_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
