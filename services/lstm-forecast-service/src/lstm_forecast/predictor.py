"""Predictor implementations for failure probability estimation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .config import Settings


@dataclass(frozen=True)
class PredictorResult:
    """Result of a failure probability prediction."""

    failure_probability: float
    confidence: float
    model_name: str
    model_version: str
    model_mode: str
    architecture: list[str]


class FailurePredictor(Protocol):
    """Protocol for interchangeable model predictors."""

    def predict(self, sequence: list[list[float]]) -> PredictorResult:
        """Predict failure probability from normalized sequence."""


class SurrogateLSTMPredictor:
    """Non-trained approximation used before real LSTM artifacts are available."""

    ARCHITECTURE = [
        "Input(time_steps, features=4)",
        "LSTM(64, return_sequences=True)",
        "Dropout(0.2)",
        "LSTM(32)",
        "Dense(16, relu)",
        "Dense(1, sigmoid)",
    ]

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def predict(self, sequence: list[list[float]]) -> PredictorResult:
        latest = sequence[-1]
        first = sequence[0]

        latest_risk = (0.35 * latest[0]) + (0.30 * latest[1]) + (0.20 * latest[2]) + (0.15 * latest[3])

        slopes = [abs(latest[i] - first[i]) / max(1.0, float(len(sequence) - 1)) for i in range(4)]
        trend_risk = (0.35 * slopes[0]) + (0.30 * slopes[1]) + (0.20 * slopes[2]) + (0.15 * slopes[3])

        probability = self._clamp((0.75 * latest_risk) + (0.25 * trend_risk))
        confidence = self._clamp(0.45 + (0.01 * len(sequence)))

        return PredictorResult(
            failure_probability=round(probability, 4),
            confidence=round(confidence, 4),
            model_name="surrogate_lstm_forecaster",
            model_version="v0",
            model_mode="surrogate",
            architecture=self.ARCHITECTURE,
        )


class KerasLSTMPredictor:
    """Loads and runs a pre-trained Keras .h5 model (no training in this service)."""

    ARCHITECTURE = [
        "Input(time_steps, features=4)",
        "LSTM(64, return_sequences=True)",
        "Dropout(0.2)",
        "LSTM(32)",
        "Dense(16, relu)",
        "Dense(1, sigmoid)",
    ]

    def __init__(self, model_path: str):
        try:
            import tensorflow as tf
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("TensorFlow is required for keras predictor mode") from exc

        self._tf = tf
        self._model = tf.keras.models.load_model(model_path)

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def predict(self, sequence: list[list[float]]) -> PredictorResult:
        tensor = self._tf.convert_to_tensor([sequence], dtype=self._tf.float32)
        raw = float(self._model(tensor, training=False).numpy()[0][0])
        probability = round(self._clamp(raw), 4)

        return PredictorResult(
            failure_probability=probability,
            confidence=0.95,
            model_name="lstm_failure_predictor",
            model_version="v1",
            model_mode="keras",
            architecture=self.ARCHITECTURE,
        )


class PredictorFactory:
    """Creates predictor based on runtime configuration."""

    @staticmethod
    def create(settings: Settings) -> FailurePredictor:
        mode = settings.predictor_mode.strip().lower()
        if mode == "keras":
            if not settings.keras_model_path:
                raise RuntimeError("FORECAST_KERAS_MODEL_PATH must be set in keras mode")
            return KerasLSTMPredictor(settings.keras_model_path)
        if mode == "torch":
            if not settings.torch_model_path:
                raise RuntimeError("FORECAST_TORCH_MODEL_PATH must be set in torch mode")
            return TorchLSTMPredictor(settings.torch_model_path)

        return SurrogateLSTMPredictor()


class TorchLSTMPredictor:
    """Loads and runs a pre-trained PyTorch LSTM model."""

    ARCHITECTURE = [
        "Input(time_steps, features=4)",
        "LSTM(64, return_sequences=True)",
        "Dropout(0.2)",
        "LSTM(32)",
        "Dense(16, relu)",
        "Dense(1, sigmoid)",
    ]

    @staticmethod
    def _resolve_path(model_path: str) -> Path:
        """Resolve model path from cwd or repository root."""

        direct = Path(model_path)
        if direct.exists():
            return direct

        if not direct.is_absolute():
            repo_root = Path(__file__).resolve().parents[4]
            candidate = repo_root / direct
            if candidate.exists():
                return candidate

        return direct

    def __init__(self, model_path: str):
        try:
            import torch
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyTorch is required for torch predictor mode") from exc

        self._torch = torch
        model_file = self._resolve_path(model_path)
        if not model_file.exists():
            raise RuntimeError(f"Torch model file not found: {model_file}")

        checkpoint = torch.load(model_file, map_location="cpu")
        input_size = int(checkpoint.get("input_size", 4))

        class _TorchNet(torch.nn.Module):
            def __init__(self, in_features: int):
                super().__init__()
                self.lstm1 = torch.nn.LSTM(input_size=in_features, hidden_size=64, batch_first=True)
                self.dropout = torch.nn.Dropout(0.2)
                self.lstm2 = torch.nn.LSTM(input_size=64, hidden_size=32, batch_first=True)
                self.fc1 = torch.nn.Linear(32, 16)
                self.relu = torch.nn.ReLU()
                self.fc2 = torch.nn.Linear(16, 1)
                self.sigmoid = torch.nn.Sigmoid()

            def forward(self, x):
                x, _ = self.lstm1(x)
                x = self.dropout(x)
                x, _ = self.lstm2(x)
                x = x[:, -1, :]
                x = self.fc1(x)
                x = self.relu(x)
                x = self.fc2(x)
                return self.sigmoid(x)

        self._model = _TorchNet(input_size)
        self._model.load_state_dict(checkpoint["state_dict"])
        self._model.eval()
        self._checkpoint = checkpoint

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    def predict(self, sequence: list[list[float]]) -> PredictorResult:
        with self._torch.no_grad():
            tensor = self._torch.tensor([sequence], dtype=self._torch.float32)
            raw = float(self._model(tensor).cpu().numpy()[0][0])

        probability = round(self._clamp(raw), 4)
        return PredictorResult(
            failure_probability=probability,
            confidence=0.98,
            model_name="lstm_failure_predictor_torch",
            model_version="v1",
            model_mode="torch",
            architecture=self.ARCHITECTURE,
        )
