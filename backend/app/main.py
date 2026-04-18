import logging
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from redis import Redis

from app.config import settings
from app.queue import QueuePublisher


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger(__name__)

app = FastAPI(title="n8n queue integration backend")

redis_client = Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    decode_responses=True,
)
publisher = QueuePublisher(
    redis_client=redis_client,
    queue_name=settings.queue_name,
    max_retries=settings.publish_max_retries,
    retry_backoff_seconds=settings.publish_retry_backoff_seconds,
    dedupe_ttl_seconds=settings.queue_dedupe_ttl_seconds,
)

upload_dir = Path(settings.upload_dir)
upload_dir.mkdir(parents=True, exist_ok=True)
_CHUNK_SIZE = 1024 * 1024


def _publish_in_background(document_id: str, file_path: str) -> None:
    try:
        publisher.publish_upload_event(document_id=document_id, file_path=file_path)
    except Exception:
        LOGGER.exception(
            "Queue publish background failure",
            extra={
                "event": "queue_publish_background_failure",
                "document_id": document_id,
                "file_path": file_path,
            },
        )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    try:
        redis_client.ping()
    except RedisError:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "ok"}


@app.post("/upload", status_code=202)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_id: str | None = Form(default=None),
) -> dict[str, str]:
    resolved_document_id = document_id or str(uuid4())
    stored_name = f"{uuid4().hex}.bin"
    root_dir = upload_dir.resolve()
    destination = (root_dir / stored_name).resolve()
    if not destination.is_relative_to(root_dir):
        raise HTTPException(status_code=400, detail="Invalid destination path")

    size_bytes = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > settings.max_upload_size_bytes:
                    raise HTTPException(status_code=413, detail="Uploaded file is too large")
                output.write(chunk)
    except HTTPException:
        if destination.exists():
            destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    file_path = str(destination)
    LOGGER.info(
        "File upload stored",
        extra={
            "event": "file_upload_stored",
            "document_id": resolved_document_id,
            "file_path": file_path,
            "size_bytes": size_bytes,
        },
    )

    background_tasks.add_task(_publish_in_background, resolved_document_id, file_path)
    LOGGER.info(
        "Queue publish scheduled",
        extra={
            "event": "queue_publish_scheduled",
            "document_id": resolved_document_id,
            "file_path": file_path,
            "queue": settings.queue_name,
        },
    )

    return {
        "status": "accepted",
        "document_id": resolved_document_id,
        "file_path": file_path,
    }
