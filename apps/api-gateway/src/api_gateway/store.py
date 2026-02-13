"""In-memory read model store for API gateway aggregation endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock

from .schemas import Asset, AssetForecast, AssetHealth, CreateAssetRequest, MaintenanceVerification


@dataclass
class StoreSnapshot:
    """Mutable store state."""

    assets: dict[str, Asset]
    health: dict[str, AssetHealth]
    forecasts: dict[str, AssetForecast]
    verifications: dict[str, MaintenanceVerification]


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

        with self._lock:
            self._snapshot = StoreSnapshot(
                assets={asset_1.asset_id: asset_1, asset_2.asset_id: asset_2},
                health={health_1.asset_id: health_1, health_2.asset_id: health_2},
                forecasts={forecast_1.asset_id: forecast_1, forecast_2.asset_id: forecast_2},
                verifications={verification.maintenance_id: verification},
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


_store = InMemoryGatewayStore()


def get_store() -> InMemoryGatewayStore:
    """Return singleton gateway store."""

    return _store
