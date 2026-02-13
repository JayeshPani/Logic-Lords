"""Mamdani fuzzy inference engine with centroid defuzzification."""

from dataclasses import dataclass

from .config import Settings
from .schemas import FuzzyInputs


@dataclass(frozen=True)
class Rule:
    """One fuzzy rule with antecedents and consequent output label."""

    name: str
    antecedents: list[tuple[str, str]]
    consequent: str


@dataclass(frozen=True)
class FuzzyResult:
    """Computed fuzzy output."""

    final_risk_score: float
    risk_level: str
    rule_activations: list[dict[str, float | str]]


class MamdaniFuzzyEngine:
    """Evaluates risk using configured membership functions and rules."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.rules = self._build_rules()

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @staticmethod
    def _triangular(x: float, a: float, b: float, c: float) -> float:
        if x < a or x > c:
            return 0.0

        if a == b and x <= b:
            return (c - x) / (c - b) if c > b else 1.0
        if b == c and x >= b:
            return (x - a) / (b - a) if b > a else 1.0

        if x == b:
            return 1.0
        if x < b:
            return (x - a) / (b - a) if b > a else 0.0
        return (c - x) / (c - b) if c > b else 0.0

    @staticmethod
    def _trapezoidal(x: float, a: float, b: float, c: float, d: float) -> float:
        if x < a or x > d:
            return 0.0
        if b <= x <= c:
            return 1.0
        if a <= x < b:
            return (x - a) / (b - a) if b > a else 1.0
        return (d - x) / (d - c) if d > c else 1.0

    def _fuzzify(self, inputs: FuzzyInputs) -> dict[str, dict[str, float]]:
        return {
            "strain": {
                "low": self._triangular(inputs.strain, 0.0, 0.0, 0.3),
                "moderate": self._triangular(inputs.strain, 0.2, 0.5, 0.7),
                "high": self._triangular(inputs.strain, 0.6, 0.8, 0.9),
                "critical": self._trapezoidal(inputs.strain, 0.85, 0.9, 1.0, 1.0),
            },
            "vibration": {
                "stable": self._triangular(inputs.vibration, 0.0, 0.0, 0.3),
                "elevated": self._triangular(inputs.vibration, 0.2, 0.5, 0.7),
                "severe": self._trapezoidal(inputs.vibration, 0.6, 0.8, 1.0, 1.0),
            },
            "temperature": {
                "normal": self._triangular(inputs.temperature, 0.0, 0.0, 0.4),
                "warm": self._triangular(inputs.temperature, 0.3, 0.5, 0.7),
                "hot": self._triangular(inputs.temperature, 0.6, 0.8, 0.9),
                "extreme": self._trapezoidal(inputs.temperature, 0.85, 0.9, 1.0, 1.0),
            },
            "rainfall": {
                "none": self._triangular(inputs.rainfall_intensity, 0.0, 0.0, 0.2),
                "light": self._triangular(inputs.rainfall_intensity, 0.1, 0.4, 0.6),
                "heavy": self._trapezoidal(inputs.rainfall_intensity, 0.5, 0.7, 1.0, 1.0),
            },
            "traffic": {
                "low": self._triangular(inputs.traffic_density, 0.0, 0.0, 0.3),
                "medium": self._triangular(inputs.traffic_density, 0.2, 0.5, 0.7),
                "high": self._trapezoidal(inputs.traffic_density, 0.6, 0.8, 1.0, 1.0),
            },
            "failure_probability": {
                "low": self._triangular(inputs.failure_probability, 0.0, 0.0, 0.4),
                "medium": self._triangular(inputs.failure_probability, 0.3, 0.5, 0.7),
                "high": self._trapezoidal(inputs.failure_probability, 0.6, 0.8, 1.0, 1.0),
            },
            "anomaly": {
                "normal": self._triangular(inputs.anomaly_score, 0.0, 0.0, 0.4),
                "abnormal": self._triangular(inputs.anomaly_score, 0.3, 0.6, 0.8),
                "severe": self._trapezoidal(inputs.anomaly_score, 0.7, 0.85, 1.0, 1.0),
            },
        }

    def _output_membership(self, label: str, x: float) -> float:
        if label == "very_low":
            return self._trapezoidal(x, 0.0, 0.0, 0.1, 0.2)
        if label == "low":
            return self._triangular(x, 0.2, 0.3, 0.4)
        if label == "moderate":
            return self._triangular(x, 0.4, 0.5, 0.6)
        if label == "high":
            return self._triangular(x, 0.6, 0.7, 0.8)
        return self._trapezoidal(x, 0.8, 0.9, 1.0, 1.0)

    @staticmethod
    def _risk_level(score: float) -> str:
        if score <= 0.2:
            return "Very Low"
        if score <= 0.4:
            return "Low"
        if score <= 0.6:
            return "Moderate"
        if score <= 0.8:
            return "High"
        return "Critical"

    @staticmethod
    def _build_rules() -> list[Rule]:
        return [
            Rule("R1", [("strain", "low"), ("vibration", "stable")], "low"),
            Rule("R2", [("strain", "moderate"), ("temperature", "warm")], "moderate"),
            Rule("R3", [("strain", "high"), ("traffic", "high")], "high"),
            Rule("R4", [("rainfall", "heavy"), ("vibration", "severe")], "critical"),
            Rule("R5", [("failure_probability", "high")], "critical"),
            Rule("R6", [("anomaly", "severe")], "critical"),
            Rule("R7", [("temperature", "extreme"), ("strain", "high")], "critical"),
            Rule("R8", [("traffic", "medium"), ("strain", "moderate"), ("vibration", "elevated")], "moderate"),
            Rule("R9", [("rainfall", "light"), ("traffic", "high"), ("strain", "moderate")], "high"),
            Rule("R10", [("anomaly", "abnormal"), ("failure_probability", "medium")], "high"),
            Rule("R11", [("strain", "critical")], "critical"),
            Rule("R12", [("vibration", "severe"), ("temperature", "hot")], "high"),
            Rule("R13", [("failure_probability", "low"), ("anomaly", "normal"), ("strain", "low")], "very_low"),
            Rule("R14", [("temperature", "normal"), ("rainfall", "none"), ("traffic", "low")], "very_low"),
            Rule("R15", [("failure_probability", "medium"), ("anomaly", "normal")], "moderate"),
        ]

    def evaluate(self, inputs: FuzzyInputs | dict[str, float]) -> FuzzyResult:
        payload = inputs if isinstance(inputs, FuzzyInputs) else FuzzyInputs.model_validate(inputs)
        memberships = self._fuzzify(payload)

        activations: list[dict[str, float | str]] = []
        xs = [i / (self.settings.centroid_resolution - 1) for i in range(self.settings.centroid_resolution)]
        aggregated = [0.0 for _ in xs]

        for rule in self.rules:
            values = [memberships[var][label] for (var, label) in rule.antecedents]
            activation = min(values) if values else 0.0
            if activation <= 0:
                continue

            activations.append(
                {
                    "name": rule.name,
                    "activation": round(activation, 4),
                    "consequent": rule.consequent,
                }
            )

            for idx, x in enumerate(xs):
                clipped = min(activation, self._output_membership(rule.consequent, x))
                aggregated[idx] = max(aggregated[idx], clipped)

        denominator = sum(aggregated)
        if denominator <= 1e-9:
            centroid = 0.0
        else:
            numerator = sum(x * mu for x, mu in zip(xs, aggregated, strict=False))
            centroid = numerator / denominator

        centroid = round(self._clamp(centroid), 4)
        return FuzzyResult(
            final_risk_score=centroid,
            risk_level=self._risk_level(centroid),
            rule_activations=activations,
        )
