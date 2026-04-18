import os


class Settings:
    redis_host = os.getenv("BACKEND_REDIS_HOST", "redis")
    redis_port = int(os.getenv("BACKEND_REDIS_PORT", "6379"))
    queue_name = os.getenv("BACKEND_QUEUE_NAME", "n8n:file_uploads")
    upload_dir = os.getenv("BACKEND_UPLOAD_DIR", "/data/uploads")
    publish_max_retries = int(os.getenv("BACKEND_PUBLISH_MAX_RETRIES", "5"))
    publish_retry_backoff_seconds = float(
        os.getenv("BACKEND_PUBLISH_RETRY_BACKOFF_SECONDS", "0.5")
    )
    queue_dedupe_ttl_seconds = int(
        os.getenv("BACKEND_QUEUE_DEDUPE_TTL_SECONDS", "86400")
    )


settings = Settings()
