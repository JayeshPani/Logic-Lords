"""SQLAlchemy models for asset registry bounded context."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Asset(Base):
    """Infrastructure asset metadata record."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    asset_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    zone: Mapped[str] = mapped_column(String(64), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sensors: Mapped[list["SensorNode"]] = relationship(back_populates="asset", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('bridge', 'road', 'tunnel', 'flyover', 'other')",
            name="ck_assets_asset_type",
        ),
        CheckConstraint(
            "status IN ('active', 'maintenance', 'retired')",
            name="ck_assets_status",
        ),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_assets_latitude"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_assets_longitude"),
    )


class SensorNode(Base):
    """Sensor device metadata linked to an asset."""

    __tablename__ = "sensor_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sensor_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(36), ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False)
    gateway_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    calibration: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    installed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    asset: Mapped[Asset] = relationship(back_populates="sensors")

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'faulty', 'decommissioned')",
            name="ck_sensor_nodes_status",
        ),
    )
