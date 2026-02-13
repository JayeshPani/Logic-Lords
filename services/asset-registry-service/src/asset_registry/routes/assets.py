"""Asset routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db_session
from ..repositories import AssetRepository, ConflictError, NotFoundError
from ..schemas import (
    AssetType,
    AssetStatus,
    CreateAssetRequest,
    CreateAssetResponse,
    ErrorResponse,
    HealthResponse,
    ListAssetsResponse,
    PaginationMeta,
    UpdateAssetStatusRequest,
)

router = APIRouter(tags=["assets"])


def _to_asset_response_item(asset):
    return {
        "asset_id": asset.asset_id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "status": asset.status,
        "zone": asset.zone,
        "location": {"lat": asset.latitude, "lon": asset.longitude},
        "metadata": asset.metadata_json,
        "installed_at": asset.installed_at,
        "created_at": asset.created_at,
        "updated_at": asset.updated_at,
    }


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}})


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        service=settings.service_name,
        version=settings.service_version,
        timestamp=datetime.now(tz=timezone.utc),
    )


@router.post(
    "/assets",
    response_model=CreateAssetResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def create_asset(payload: CreateAssetRequest, session: Session = Depends(get_db_session)) -> CreateAssetResponse:
    repo = AssetRepository(session)
    try:
        asset = repo.create_asset(payload)
    except ConflictError:
        return _error(status.HTTP_409_CONFLICT, "CONFLICT", "Asset already exists")

    return CreateAssetResponse(data=_to_asset_response_item(asset))


@router.get("/assets", response_model=ListAssetsResponse)
def list_assets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    zone: str | None = Query(default=None, min_length=1, max_length=64),
    asset_type: AssetType | None = Query(default=None),
    status_filter: AssetStatus | None = Query(default=None, alias="status"),
    session: Session = Depends(get_db_session),
) -> ListAssetsResponse:
    repo = AssetRepository(session)
    assets, total_items = repo.list_assets(page, page_size, zone, asset_type, status_filter)
    total_pages = (total_items + page_size - 1) // page_size
    return ListAssetsResponse(
        data=[_to_asset_response_item(asset) for asset in assets],
        pagination=PaginationMeta(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
        ),
    )


@router.get("/assets/{asset_id}", response_model=CreateAssetResponse, responses={404: {"model": ErrorResponse}})
def get_asset(asset_id: str, session: Session = Depends(get_db_session)) -> CreateAssetResponse:
    repo = AssetRepository(session)
    try:
        asset = repo.get_asset_by_asset_id(asset_id)
    except NotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Asset not found")

    return CreateAssetResponse(data=_to_asset_response_item(asset))


@router.patch(
    "/assets/{asset_id}/status",
    response_model=CreateAssetResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_asset_status(
    asset_id: str,
    payload: UpdateAssetStatusRequest,
    session: Session = Depends(get_db_session),
) -> CreateAssetResponse:
    repo = AssetRepository(session)
    try:
        asset = repo.update_asset_status(asset_id, payload.status)
    except NotFoundError:
        return _error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Asset not found")

    return CreateAssetResponse(data=_to_asset_response_item(asset))
