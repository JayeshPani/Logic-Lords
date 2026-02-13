"""Final output composer for AI risk pipeline."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ComposedOutput:
    """Final computed output object."""

    health_score: float
    risk_level: str


class OutputComposer:
    """Maps final risk score to human-readable risk level."""

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

    def compose(self, final_risk_score: float) -> ComposedOutput:
        score = max(0.0, min(1.0, final_risk_score))
        return ComposedOutput(health_score=round(score, 4), risk_level=self._risk_level(score))
