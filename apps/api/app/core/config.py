from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "TRAMA"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "local"

    DATABASE_URL: str = "postgresql+psycopg2://trama:trama@postgres:5432/trama"

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    DISCOVERY_DEADLINE_SECONDS: int = Field(default=120, ge=30, le=300)
    DISCOVERY_TOP_K: int = Field(default=5, ge=1, le=10)
    DISCOVERY_LLM_ENABLED: bool = False
    WORKER_POLL_SECONDS: float = Field(default=2.0, ge=0.2, le=30)
    MONITOR_FETCH_SECONDS: float = Field(default=20.0, ge=2, le=30)

    # LLM (provider abstraction; Gemini Flash free tier for MVP tests).
    # Startup must not break when the key is absent — validation happens
    # at the provider factory boundary, not here.
    LLM_PROVIDER: str = "gemini"
    LLM_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_API_KEY: str = ""
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_RETRIES: int = 2
    LLM_MAX_OUTPUT_TOKENS: int = 1024
    LLM_TELEMETRY_ENABLED: bool = True


settings = Settings()
