"""FastAPI app for fuzzy inference service."""

from fastapi import FastAPI

from .config import get_settings
from .observability import configure_logging
from .routes import router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title=settings.service_name, version=settings.service_version)
app.include_router(router)
