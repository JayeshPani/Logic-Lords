"""Runtime configuration for forecast service."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service settings loaded from environment variables."""

    service_name: str = "lstm-forecast-service"
    service_version: str = "0.3.0"

    predictor_mode: str = "torch"
    keras_model_path: str | None = None
    torch_model_path: str | None = "data-platform/ml/models/lstm_failure_predictor.pt"
    torch_meta_path: str | None = "data-platform/ml/models/lstm_failure_predictor.meta.json"
    fallback_to_surrogate_on_startup_error: bool = True

    history_window_hours: int = 48
    horizon_hours: int = 72
    min_sequence_points: int = 16
    log_level: str = "INFO"
    metrics_enabled: bool = True
    event_produced_by: str = "services/lstm-forecast-service"
    min_model_confidence: float = Field(default=0.0, ge=0, le=1)

    strain_min: float = 0.0
    strain_max: float = 2000.0
    vibration_min: float = 0.0
    vibration_max: float = 10.0
    temperature_min: float = -20.0
    temperature_max: float = 80.0
    humidity_min: float = 0.0
    humidity_max: float = 100.0

    model_config = SettingsConfigDict(env_prefix="FORECAST_", extra="ignore")


def get_settings() -> Settings:
    """Return settings object."""

    return Settings()
