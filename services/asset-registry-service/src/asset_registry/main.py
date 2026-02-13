"""FastAPI application entrypoint for asset registry service."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_settings
from .db import init_db
from .routes.assets import router as assets_router
from .routes.sensors import router as sensors_router

settings = get_settings()

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize persistence during application startup."""
    init_db()
    yield


app = FastAPI(title=settings.service_name, version=settings.service_version, lifespan=lifespan)
app.include_router(assets_router)
app.include_router(sensors_router)
