from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.responses import JSONResponse

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
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    messages = {
        "invalid_request": ("Confira os dados informados.", False),
        "not_found": ("Registro não encontrado.", False),
        "conflict": (
            "A operação conflita com o estado atual. Atualize os dados e tente novamente.",
            False,
        ),
        "rate_limited": (
            "Limite temporário atingido. Tente novamente mais tarde.",
            True,
        ),
        "source_unavailable": ("A fonte está indisponível no momento.", True),
        "timeout": ("O prazo de processamento foi excedido.", True),
        "internal_error": ("Não foi possível concluir a operação.", True),
    }

    def error_response(code, status):
        message, retryable = messages[code]
        return JSONResponse(
            status_code=status,
            content={
                "error": {"code": code, "message": message, "retryable": retryable}
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo input, validation context, tokens or raw source content.
        return error_response("invalid_request", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code")
        if code not in messages:
            code = {404: "not_found", 429: "rate_limited"}.get(
                exc.status_code, "invalid_request"
            )
        return error_response(code, exc.status_code)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return error_response("internal_error", 500)

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
