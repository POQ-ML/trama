from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.schemas.health import HealthResponse

router = APIRouter()


def _check_db() -> str:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return "up"
    except Exception:
        return "down"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="trama-api",
        environment=settings.ENVIRONMENT,
        database=_check_db(),
    )
