"""Isolation Forest based anomaly detector with heuristic fallback."""

from dataclasses import dataclass
import json
import math
from pathlib import Path
from statistics import fmean, pstdev

from .config import Settings
from .schemas import NormalizedFeatures


@dataclass(frozen=True)
class AnomalyResult:
    """Result returned by the anomaly detector."""

    anomaly_score: float
    anomaly_flag: int
    threshold: float
    detector_mode: str


class AnomalyDetector:
    """Detects abnormal behavior using Isolation Forest when available."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._has_sklearn = False
        self._if_cls = None
        self._pretrained_model = None
        self._pretrained_decision_min = None
        self._pretrained_decision_max = None

        try:
            from sklearn.ensemble import IsolationForest

            self._if_cls = IsolationForest
            self._has_sklearn = True
        except Exception:
            self._has_sklearn = False

        self._load_pretrained_model()

    def _load_pretrained_model(self) -> None:
        """Load a pre-trained Isolation Forest model when configured."""

        if not self.settings.pretrained_model_path:
            return

        model_path = self._resolve_path(self.settings.pretrained_model_path)
        if not model_path.exists():
            return

        try:
            import joblib
        except Exception:  # pragma: no cover
            return

        self._pretrained_model = joblib.load(model_path)

        if self.settings.pretrained_meta_path:
            meta_path = self._resolve_path(self.settings.pretrained_meta_path)
            if meta_path.exists():
                try:
                    meta = json.loads(meta_path.read_text())
                    self._pretrained_decision_min = float(meta.get("decision_min"))
                    self._pretrained_decision_max = float(meta.get("decision_max"))
                except Exception:
                    self._pretrained_decision_min = None
                    self._pretrained_decision_max = None

    @staticmethod
    def _resolve_path(path_str: str) -> Path:
        """Resolve configured file path from cwd or repository root."""

        direct = Path(path_str)
        if direct.exists():
            return direct

        if not direct.is_absolute():
            repo_root = Path(__file__).resolve().parents[4]
            candidate = repo_root / direct
            if candidate.exists():
                return candidate

        return direct

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _as_vector(features: NormalizedFeatures | dict[str, float]) -> list[float]:
        payload = features if isinstance(features, NormalizedFeatures) else NormalizedFeatures.model_validate(features)
        return [payload.strain, payload.vibration, payload.temperature, payload.humidity]

    @staticmethod
    def _sigmoid(value: float) -> float:
        return 1.0 / (1.0 + math.exp(-value))

    def _heuristic_score(self, current: list[float], baseline: list[list[float]]) -> float:
        base_score = (0.35 * current[0]) + (0.35 * current[1]) + (0.15 * current[2]) + (0.15 * current[3])

        if not baseline:
            return self._clamp(base_score)

        z_scores: list[float] = []
        for col in range(4):
            series = [row[col] for row in baseline]
            mean = fmean(series)
            std = pstdev(series)
            if std <= 1e-6:
                z = abs(current[col] - mean)
            else:
                z = abs(current[col] - mean) / std
            z_scores.append(min(z, 6.0) / 6.0)

        deviation = fmean(z_scores)
        score = (0.45 * base_score) + (0.55 * deviation)
        return self._clamp(score)

    def _isolation_forest_score(self, current: list[float], baseline: list[list[float]]) -> float:
        model = self._if_cls(
            n_estimators=self.settings.n_estimators,
            contamination=self.settings.contamination,
            random_state=self.settings.random_state,
        )
        model.fit(baseline)

        current_decision = float(model.decision_function([current])[0])
        baseline_decisions = [float(value) for value in model.decision_function(baseline)]

        highest = max(baseline_decisions)
        lowest = min(baseline_decisions)

        if (highest - lowest) <= 1e-9:
            normalized_inverse = self._sigmoid(-5.0 * current_decision)
        else:
            normalized_inverse = (highest - current_decision) / (highest - lowest)

        score = normalized_inverse
        return self._clamp(score)

    def _pretrained_model_score(self, current: list[float]) -> float:
        """Compute anomaly score from a pre-trained model and calibration metadata."""

        decision = float(self._pretrained_model.decision_function([current])[0])

        if (
            self._pretrained_decision_min is None
            or self._pretrained_decision_max is None
            or (self._pretrained_decision_max - self._pretrained_decision_min) <= 1e-9
        ):
            return self._clamp(self._sigmoid(-5.0 * decision))

        normalized_inverse = (
            self._pretrained_decision_max - decision
        ) / (self._pretrained_decision_max - self._pretrained_decision_min)
        return self._clamp(normalized_inverse)

    def detect(
        self,
        current: NormalizedFeatures | dict[str, float],
        baseline_window: list[NormalizedFeatures] | list[dict[str, float]] | None = None,
    ) -> AnomalyResult:
        baseline_window = baseline_window or []
        current_vec = self._as_vector(current)
        baseline_vecs = [self._as_vector(row) for row in baseline_window]

        if self._pretrained_model is not None:
            score = self._pretrained_model_score(current_vec)
            mode = "isolation_forest"
        else:
            use_iforest = self._has_sklearn and len(baseline_vecs) >= self.settings.min_baseline_points

            if use_iforest:
                score = self._isolation_forest_score(current_vec, baseline_vecs)
                mode = "isolation_forest"
            else:
                score = self._heuristic_score(current_vec, baseline_vecs)
                mode = "heuristic"

        flag = 1 if score >= self.settings.anomaly_threshold else 0

        return AnomalyResult(
            anomaly_score=round(score, 4),
            anomaly_flag=flag,
            threshold=self.settings.anomaly_threshold,
            detector_mode=mode,
        )
