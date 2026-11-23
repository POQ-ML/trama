from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.discovery import router as discovery_router
from app.api.v1.projects import router as projects_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(discovery_router, prefix=settings.API_V1_STR, tags=["discovery"])
api_router.include_router(health_router, prefix=settings.API_V1_STR, tags=["health"])

api_router.include_router(projects_router, prefix=settings.API_V1_STR, tags=["projects"])
