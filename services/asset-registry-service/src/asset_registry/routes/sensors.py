"""Sensor mapping routes."""

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..db import get_db_session
from ..repositories import AssetRepository, ConflictError, NotFoundError
from ..schemas import (
    CreateSensorMappingRequest,
    CreateSensorMappingResponse,
    ErrorResponse,
    ListSensorsResponse,
)

router = APIRouter(tags=["sensors"])


def _to_sensor_response_item(sensor, asset_public_id: str):
    return {
        "sensor_id": sensor.sensor_id,
        "asset_id": asset_public_id,
        "gateway_id": sensor.gateway_id,
        "firmware_version": sensor.firmware_version,
        "status": sensor.status,
        "calibration": sensor.calibration,
        "installed_at": sensor.installed_at,
        "last_seen_at": sensor.last_seen_at,
        "created_at": sensor.created_at,
        "updated_at": sensor.updated_at,
    }


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.post(
    "/assets/{asset_id}/sensors",
    response_model=CreateSensorMappingResponse,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def map_sensor(
    asset_id: str,
    payload: CreateSensorMappingRequest,
    session: Session = Depends(get_db_session),
) -> CreateSensorMappingResponse:
    repo = AssetRepository(session)
    try:
        sensor = repo.map_sensor_to_asset(asset_id, payload)
    except NotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Asset not found")
    except ConflictError:
        return _error(status.HTTP_409_CONFLICT, "CONFLICT", "Sensor mapping already exists")

    return CreateSensorMappingResponse(data=_to_sensor_response_item(sensor, asset_id))


@router.get(
    "/assets/{asset_id}/sensors",
    response_model=ListSensorsResponse,
    responses={404: {"model": ErrorResponse}},
)
def list_sensors(asset_id: str, session: Session = Depends(get_db_session)) -> ListSensorsResponse:
    repo = AssetRepository(session)
    try:
        sensors = repo.list_sensors_for_asset(asset_id)
    except NotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Asset not found")

    return ListSensorsResponse(data=[_to_sensor_response_item(sensor, asset_id) for sensor in sensors])
