"""Pydantic schemas for HTTP request and response models."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AssetType = Literal["bridge", "road", "tunnel", "flyover", "other"]
AssetStatus = Literal["active", "maintenance", "retired"]
SensorStatus = Literal["active", "inactive", "faulty", "decommissioned"]


class GeoPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class CreateAssetRequest(BaseModel):
    asset_id: str = Field(pattern=r"^asset_[a-z0-9]+_[a-z0-9]+_[0-9]+$")
    name: str = Field(min_length=2, max_length=120)
    asset_type: AssetType
    zone: str = Field(min_length=1, max_length=64)
    location: GeoPoint
    metadata: dict[str, Any] = Field(default_factory=dict)
    installed_at: datetime | None = None


class AssetResponseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    name: str
    asset_type: AssetType
    status: AssetStatus
    zone: str
    location: GeoPoint
    metadata: dict[str, Any]
    installed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateAssetResponse(BaseModel):
    data: AssetResponseItem


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ListAssetsResponse(BaseModel):
    data: list[AssetResponseItem]
    pagination: PaginationMeta


class UpdateAssetStatusRequest(BaseModel):
    status: AssetStatus


class CreateSensorMappingRequest(BaseModel):
    sensor_id: str = Field(pattern=r"^sensor_[a-z0-9]+_[a-z0-9]+_[0-9]+$")
    gateway_id: str | None = Field(default=None, min_length=1, max_length=128)
    firmware_version: str | None = Field(default=None, min_length=1, max_length=32)
    status: SensorStatus = "active"
    calibration: dict[str, Any] = Field(default_factory=dict)
    installed_at: datetime | None = None


class SensorResponseItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sensor_id: str
    asset_id: str
    gateway_id: str | None
    firmware_version: str | None
    status: SensorStatus
    calibration: dict[str, Any]
    installed_at: datetime | None
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateSensorMappingResponse(BaseModel):
    data: SensorResponseItem


class ListSensorsResponse(BaseModel):
    data: list[SensorResponseItem]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
