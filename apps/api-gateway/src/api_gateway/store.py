"""In-memory read model store for API gateway aggregation endpoints."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import random
from threading import Lock
import time

from .schemas import (
    Asset,
    AssetForecast,
    AssetHealth,
    CreateAssetRequest,
    LstmForecastPoint,
    LstmRealtimeData,
    LstmRealtimeModelInfo,
    LstmRealtimeSensorPoint,
    MaintenanceVerification,
)


@dataclass
class StoreSnapshot:
    """Mutable store state."""

    assets: dict[str, Asset]
    health: dict[str, AssetHealth]
    forecasts: dict[str, AssetForecast]
    verifications: dict[str, MaintenanceVerification]
    lstm_realtime: LstmRealtimeData


@dataclass(frozen=True)
class _Sample:
    timestamp: datetime
    strain_value: float
    vibration_rms: float
    temperature: float
    humidity: float


class _LstmRealtimeGenerator:
    """Generates realistic synthetic telemetry and 72h forecast on demand."""

    def __init__(self, *, asset_id: str, seed: int = 23) -> None:
        self._asset_id = asset_id
        self._rng = random.Random(seed)
        self._sample_minutes = 5
        self._tick_seconds = 3.0
        self._history: deque[_Sample] = deque(maxlen=int((48 * 60) / self._sample_minutes))

        self._sim_time = datetime.now(tz=timezone.utc) - timedelta(hours=48)
        self._t = 0.0
        self._temp_bias = self._rng.uniform(-1.0, 1.0)
        self._hum_bias = self._rng.uniform(-5.0, 5.0)
        self._strain_bias = self._rng.uniform(-0.7, 0.7)
        self._vib_bias = self._rng.uniform(-0.25, 0.25)
        self._drift = 0.0
        self._event_left = 0
        self._event_scale = 0.0
        self._last_update_monotonic = time.monotonic()

        sample_seconds = self._sample_minutes * 60
        for _ in range(self._history.maxlen):
            self._history.append(self._next_sample(sample_seconds))

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    def _next_sample(self, step_seconds: float) -> _Sample:
        self._sim_time += timedelta(seconds=step_seconds)
        self._t += step_seconds
        hour = self._sim_time.hour + (self._sim_time.minute / 60.0)
        daily = (2.0 * math.pi * hour) / 24.0

        if self._event_left <= 0 and self._rng.random() < 0.016:
            self._event_left = self._rng.randint(5, 18)
            self._event_scale = self._rng.uniform(0.35, 1.1)
        if self._event_left > 0:
            self._event_left -= 1
        event_boost = self._event_scale if self._event_left > 0 else 0.0

        rain_wave = max(0.0, math.sin(self._t / 2100.0 + 0.7))
        rainfall = self._clamp((rain_wave**2) * self._rng.uniform(0.0, 8.0), 0.0, 18.0)

        commuter = max(0.0, math.sin((hour - 7.7) / 2.2)) + max(0.0, math.sin((hour - 17.3) / 2.4))
        traffic = self._clamp(0.25 + 0.45 * commuter + self._rng.uniform(-0.05, 0.06), 0.0, 1.0)

        temperature = (
            26.0
            + 6.1 * math.sin(daily - 0.75)
            + 1.4 * math.sin(self._t / 860.0)
            - 0.36 * rainfall
            + self._temp_bias
            + self._rng.gauss(0.0, 0.32)
        )
        humidity = (
            57.0
            + 13.2 * math.cos(daily + 0.42)
            - 0.63 * (temperature - 26.0)
            + 2.0 * rainfall
            + self._hum_bias
            + self._rng.gauss(0.0, 1.0)
        )
        vibration = (
            2.7
            + 3.0 * traffic
            + 0.9 * math.sin(self._t / 150.0)
            + 0.62 * (rainfall / 10.0)
            + 1.4 * event_boost
            + self._vib_bias
            + self._rng.gauss(0.0, 0.16)
        )

        self._drift = (0.996 * self._drift) + self._rng.uniform(-0.006, 0.009)
        strain = (
            8.0
            + 1.52 * max(temperature - 24.0, 0.0)
            + 1.27 * vibration
            + 1.7 * self._drift
            + 1.2 * event_boost
            + self._strain_bias
            + self._rng.gauss(0.0, 0.22)
        )

        return _Sample(
            timestamp=self._sim_time,
            strain_value=round(self._clamp(strain, 2.0, 40.0), 4),
            vibration_rms=round(self._clamp(vibration, 0.3, 16.0), 4),
            temperature=round(self._clamp(temperature, -4.0, 56.0), 4),
            humidity=round(self._clamp(humidity, 6.0, 98.0), 4),
        )

    def _advance(self) -> None:
        now_mono = time.monotonic()
        elapsed = max(0.0, now_mono - self._last_update_monotonic)
        steps = max(1, int(elapsed // self._tick_seconds))
        sample_seconds = self._sample_minutes * 60
        for _ in range(steps):
            self._history.append(self._next_sample(sample_seconds))
        self._last_update_monotonic = now_mono

    def _current_probability(self) -> float:
        latest = self._history[-1]
        baseline = self._history[0]
        latest_score = (
            0.34 * (latest.strain_value / 22.0)
            + 0.31 * (latest.vibration_rms / 8.0)
            + 0.20 * ((latest.temperature - 18.0) / 25.0)
            + 0.15 * (latest.humidity / 100.0)
        )
        drift_score = (
            abs(latest.strain_value - baseline.strain_value) / 20.0
            + abs(latest.vibration_rms - baseline.vibration_rms) / 7.0
        )
        return self._clamp((0.72 * latest_score) + (0.28 * drift_score), 0.02, 0.99)

    def _forecast(self, base_p: float) -> list[LstmForecastPoint]:
        points: list[LstmForecastPoint] = []
        for hour in range(0, 73, 6):
            progress = hour / 72.0
            wave = 0.07 * math.sin((2.0 * math.pi * progress) + 0.6)
            drift = 0.13 * progress
            probability = self._clamp(base_p - 0.08 + wave + drift, 0.01, 0.99)
            points.append(LstmForecastPoint(hour=float(hour), probability=round(probability, 4)))
        return points

    def snapshot(self) -> LstmRealtimeData:
        self._advance()
        p72 = self._current_probability()
        history = [
            LstmRealtimeSensorPoint(
                timestamp=sample.timestamp,
                strain_value=sample.strain_value,
                vibration_rms=sample.vibration_rms,
                temperature=sample.temperature,
                humidity=sample.humidity,
            )
            for sample in list(self._history)
        ]
        return LstmRealtimeData(
            asset_id=self._asset_id,
            generated_at=datetime.now(tz=timezone.utc),
            history_window_hours=48,
            forecast_horizon_hours=72,
            current_failure_probability_72h=round(p72, 4),
            history=history,
            forecast_points=self._forecast(p72),
            model=LstmRealtimeModelInfo(
                name="lstm_failure_predictor",
                version="v1",
                mode="gateway-simulated",
                confidence=0.9,
            ),
            source="api-gateway-simulator",
        )


class InMemoryGatewayStore:
    """Thread-safe store backing API gateway facade."""

    def __init__(self) -> None:
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        now = datetime.now(tz=timezone.utc)
        asset_1 = Asset(
            asset_id="asset_w12_bridge_0042",
            name="West Sector Bridge 42",
            asset_type="bridge",
            status="active",
            zone="w12",
            location={"lat": 19.0728, "lon": 72.8826},
            metadata={"lanes": 4},
            installed_at=now,
            created_at=now,
            updated_at=now,
        )
        asset_2 = Asset(
            asset_id="asset_w12_road_0101",
            name="West Sector Road 101",
            asset_type="road",
            status="maintenance",
            zone="w12",
            location={"lat": 19.081, "lon": 72.891},
            metadata={"segment_km": 3.4},
            installed_at=now,
            created_at=now,
            updated_at=now,
        )

        health_1 = AssetHealth(
            asset_id=asset_1.asset_id,
            evaluated_at=now,
            health_score=0.74,
            risk_level="High",
            failure_probability_72h=0.67,
            anomaly_flag=1,
            severity="warning",
            components={
                "mechanical_stress": 0.82,
                "thermal_stress": 0.61,
                "fatigue": 0.76,
                "environmental_exposure": 0.58,
            },
            model_versions={"fuzzy": "v1", "fusion": "v1"},
        )
        health_2 = AssetHealth(
            asset_id=asset_2.asset_id,
            evaluated_at=now,
            health_score=0.41,
            risk_level="Moderate",
            failure_probability_72h=0.33,
            anomaly_flag=0,
            severity="watch",
            components={
                "mechanical_stress": 0.44,
                "thermal_stress": 0.37,
                "fatigue": 0.42,
                "environmental_exposure": 0.39,
            },
            model_versions={"fuzzy": "v1", "fusion": "v1"},
        )

        forecast_1 = AssetForecast(
            asset_id=asset_1.asset_id,
            generated_at=now,
            horizon_hours=72,
            failure_probability_72h=0.67,
            confidence=0.81,
            model={"name": "lstm_failure_forecast", "version": "v1"},
        )
        forecast_2 = AssetForecast(
            asset_id=asset_2.asset_id,
            generated_at=now,
            horizon_hours=72,
            failure_probability_72h=0.33,
            confidence=0.78,
            model={"name": "lstm_failure_forecast", "version": "v1"},
        )

        verification = MaintenanceVerification(
            maintenance_id="mnt_20260214_0012",
            asset_id=asset_1.asset_id,
            verification_status="confirmed",
            evidence_hash="0x" + "a" * 64,
            tx_hash="0x" + "b" * 64,
            network="sepolia",
            contract_address="0x" + "1" * 40,
            chain_id=11155111,
            block_number=129934,
            verified_at=now,
        )

        self._lstm_generator = _LstmRealtimeGenerator(asset_id=asset_2.asset_id)
        default_lstm = self._lstm_generator.snapshot()

        with self._lock:
            self._snapshot = StoreSnapshot(
                assets={asset_1.asset_id: asset_1, asset_2.asset_id: asset_2},
                health={health_1.asset_id: health_1, health_2.asset_id: health_2},
                forecasts={forecast_1.asset_id: forecast_1, forecast_2.asset_id: forecast_2},
                verifications={verification.maintenance_id: verification},
                lstm_realtime=default_lstm,
            )

    def list_assets(
        self,
        *,
        zone: str | None,
        asset_type: str | None,
        status: str | None,
    ) -> list[Asset]:
        with self._lock:
            items = list(self._snapshot.assets.values())

        if zone:
            items = [item for item in items if item.zone == zone]
        if asset_type:
            items = [item for item in items if item.asset_type == asset_type]
        if status:
            items = [item for item in items if item.status == status]

        return sorted(items, key=lambda item: item.asset_id)

    def create_asset(self, payload: CreateAssetRequest) -> Asset:
        now = datetime.now(tz=timezone.utc)
        with self._lock:
            if payload.asset_id in self._snapshot.assets:
                raise ValueError(f"asset already exists: {payload.asset_id}")
            asset = Asset(
                asset_id=payload.asset_id,
                name=payload.name,
                asset_type=payload.asset_type,
                status="active",
                zone=payload.zone,
                location=payload.location,
                metadata=payload.metadata,
                installed_at=payload.installed_at,
                created_at=now,
                updated_at=now,
            )
            self._snapshot.assets[asset.asset_id] = asset
            return asset

    def get_asset(self, asset_id: str) -> Asset | None:
        with self._lock:
            return self._snapshot.assets.get(asset_id)

    def get_asset_health(self, asset_id: str) -> AssetHealth | None:
        with self._lock:
            return self._snapshot.health.get(asset_id)

    def get_asset_forecast(self, asset_id: str, *, horizon_hours: int) -> AssetForecast | None:
        with self._lock:
            forecast = self._snapshot.forecasts.get(asset_id)
        if forecast is None:
            return None
        return forecast.model_copy(update={"horizon_hours": horizon_hours})

    def get_maintenance_verification(self, maintenance_id: str) -> MaintenanceVerification | None:
        with self._lock:
            return self._snapshot.verifications.get(maintenance_id)

    def set_lstm_realtime(self, payload: LstmRealtimeData) -> None:
        with self._lock:
            self._snapshot.lstm_realtime = payload

    def get_lstm_realtime(self) -> LstmRealtimeData:
        with self._lock:
            if hasattr(self, "_lstm_generator") and self._lstm_generator is not None:
                self._snapshot.lstm_realtime = self._lstm_generator.snapshot()
            return self._snapshot.lstm_realtime


_store = InMemoryGatewayStore()


def get_store() -> InMemoryGatewayStore:
    """Return singleton gateway store."""

    return _store
