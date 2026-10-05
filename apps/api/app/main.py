from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("trama.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TRAMA API starting (env=%s)", settings.ENVIRONMENT)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TRAMA API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS + ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["health"])
    def root_health():
        return {
            "status": "ok",
            "service": "trama-api",
            "environment": settings.ENVIRONMENT,
        }

    app.include_router(api_router)

    return app


app = create_app()
