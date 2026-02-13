"""Persistence operations for the asset registry context."""

from datetime import datetime, timezone

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Asset, SensorNode
from .schemas import CreateAssetRequest, CreateSensorMappingRequest


class ConflictError(Exception):
    """Raised when a unique constraint conflict occurs."""


class NotFoundError(Exception):
    """Raised when an entity cannot be found."""


class AssetRepository:
    """Repository for assets and sensor mappings."""

    def __init__(self, session: Session):
        self.session = session

    def create_asset(self, payload: CreateAssetRequest) -> Asset:
        asset = Asset(
            asset_id=payload.asset_id,
            name=payload.name,
            asset_type=payload.asset_type,
            status="active",
            zone=payload.zone,
            latitude=payload.location.lat,
            longitude=payload.location.lon,
            metadata_json=payload.metadata,
            installed_at=payload.installed_at,
        )
        self.session.add(asset)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Asset already exists or violates constraints") from exc

        self.session.refresh(asset)
        return asset

    def get_asset_by_asset_id(self, asset_id: str) -> Asset:
        stmt: Select[tuple[Asset]] = select(Asset).where(Asset.asset_id == asset_id)
        asset = self.session.scalar(stmt)
        if asset is None:
            raise NotFoundError("Asset not found")
        return asset

    def list_assets(
        self,
        page: int,
        page_size: int,
        zone: str | None,
        asset_type: str | None,
        status: str | None,
    ) -> tuple[list[Asset], int]:
        stmt = select(Asset)
        if zone:
            stmt = stmt.where(Asset.zone == zone)
        if asset_type:
            stmt = stmt.where(Asset.asset_type == asset_type)
        if status:
            stmt = stmt.where(Asset.status == status)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_items = int(self.session.scalar(count_stmt) or 0)

        offset = (page - 1) * page_size
        records = list(self.session.scalars(stmt.order_by(Asset.created_at.desc()).offset(offset).limit(page_size)))
        return records, total_items

    def update_asset_status(self, asset_id: str, status: str) -> Asset:
        asset = self.get_asset_by_asset_id(asset_id)
        asset.status = status
        asset.updated_at = datetime.now(tz=timezone.utc)
        self.session.add(asset)
        self.session.commit()
        self.session.refresh(asset)
        return asset

    def map_sensor_to_asset(self, asset_id: str, payload: CreateSensorMappingRequest) -> SensorNode:
        asset = self.get_asset_by_asset_id(asset_id)
        sensor = SensorNode(
            sensor_id=payload.sensor_id,
            asset_id=asset.id,
            gateway_id=payload.gateway_id,
            firmware_version=payload.firmware_version,
            status=payload.status,
            calibration=payload.calibration,
            installed_at=payload.installed_at,
        )
        self.session.add(sensor)

        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise ConflictError("Sensor mapping already exists or violates constraints") from exc

        self.session.refresh(sensor)
        return sensor

    def list_sensors_for_asset(self, asset_id: str) -> list[SensorNode]:
        asset = self.get_asset_by_asset_id(asset_id)
        stmt = select(SensorNode).where(SensorNode.asset_id == asset.id).order_by(SensorNode.created_at.desc())
        return list(self.session.scalars(stmt))
