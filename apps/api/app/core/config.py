from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "TRAMA"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "local"

    DATABASE_URL: str = "postgresql+psycopg2://trama:trama@postgres:5432/trama"

    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
