import os
from functools import lru_cache

from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = Field(default="Document Service API")
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/documents"
    )

    storage_type: str = Field(default="local")
    local_upload_dir: str = Field(default="./uploads")

    max_upload_size_mb: int = Field(default=10)


def _get_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_name=os.getenv("APP_NAME", "Document Service API"),
        app_env=os.getenv("APP_ENV", "development"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://postgres:postgres@localhost:5432/documents",
        ),
        storage_type=os.getenv("STORAGE_TYPE", "local"),
        local_upload_dir=os.getenv("LOCAL_UPLOAD_DIR", "./uploads"),
        max_upload_size_mb=_get_int_env("MAX_UPLOAD_SIZE_MB", 10),
    )
