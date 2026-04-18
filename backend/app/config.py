import os


def _env_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw}") from exc


def _env_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float value for {name}: {raw}") from exc


class Settings:
    redis_host = os.getenv("BACKEND_REDIS_HOST", "redis")
    redis_port = _env_int("BACKEND_REDIS_PORT", "6379")
    queue_name = os.getenv("BACKEND_QUEUE_NAME", "n8n:file_uploads")
    upload_dir = os.getenv("BACKEND_UPLOAD_DIR", "/data/uploads")
    max_upload_size_bytes = _env_int("BACKEND_MAX_UPLOAD_SIZE_BYTES", "52428800")
    publish_max_retries = _env_int("BACKEND_PUBLISH_MAX_RETRIES", "5")
    publish_retry_backoff_seconds = _env_float(
        "BACKEND_PUBLISH_RETRY_BACKOFF_SECONDS", "0.5"
    )
    queue_dedupe_ttl_seconds = _env_int(
        "BACKEND_QUEUE_DEDUPE_TTL_SECONDS", "86400"
    )


settings = Settings()
