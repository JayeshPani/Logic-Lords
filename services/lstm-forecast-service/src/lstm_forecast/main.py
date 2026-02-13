"""FastAPI app for forecast service."""

from fastapi import FastAPI

from .config import get_settings
from .routes import router

settings = get_settings()

app = FastAPI(title=settings.service_name, version=settings.service_version)
app.include_router(router)
