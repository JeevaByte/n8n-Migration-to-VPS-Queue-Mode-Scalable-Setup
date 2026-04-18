import logging
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile
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
    return {"status": "ok"}


@app.post("/upload", status_code=202)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_id: str | None = Form(default=None),
) -> dict[str, str]:
    resolved_document_id = document_id or str(uuid4())
    original_name = Path(file.filename or "upload.bin").name
    stored_name = f"{resolved_document_id}_{original_name}"
    destination = upload_dir / stored_name

    content = await file.read()
    destination.write_bytes(content)
    await file.close()

    file_path = str(destination)
    LOGGER.info(
        "File upload stored",
        extra={
            "event": "file_upload_stored",
            "document_id": resolved_document_id,
            "file_path": file_path,
            "size_bytes": len(content),
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
