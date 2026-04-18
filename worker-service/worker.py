import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from redis import Redis


logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("document-worker")


def env_int(name: str, default: str) -> int:
    raw = os.getenv(name, default)
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer value for {name}: {raw}") from exc


def env_float(name: str, default: str) -> float:
    raw = os.getenv(name, default)
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid float value for {name}: {raw}") from exc


@dataclass
class Config:
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = env_int("REDIS_PORT", "6379")
    redis_queue_name: str = os.getenv("REDIS_QUEUE_NAME", "document_processing_queue")
    redis_failed_queue_name: str = os.getenv("REDIS_FAILED_QUEUE_NAME", "document_processing_failed")
    redis_poll_timeout_seconds: int = env_int("REDIS_POLL_TIMEOUT_SECONDS", "5")
    max_retries: int = env_int("WORKER_MAX_RETRIES", "3")
    retry_backoff_seconds: float = env_float("WORKER_RETRY_BACKOFF_SECONDS", "2")
    summary_word_limit: int = env_int("SUMMARY_WORD_LIMIT", "30")

    postgres_host: str = os.getenv("POSTGRES_HOST", "postgres")
    postgres_port: int = env_int("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "n8n")
    postgres_user: str = os.getenv("POSTGRES_USER", "n8n")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "")


CONFIG = Config()


def postgres_dsn() -> str:
    return (
        f"host={CONFIG.postgres_host} "
        f"port={CONFIG.postgres_port} "
        f"dbname={CONFIG.postgres_db} "
        f"user={CONFIG.postgres_user} "
        f"password={CONFIG.postgres_password}"
    )


def ensure_schema() -> None:
    logger.info("Ensuring PostgreSQL schema exists")
    with psycopg.connect(postgres_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    raw_text TEXT,
                    structured_data JSONB,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()


class OCRProcessingError(Exception):
    pass


class LLMProcessingError(Exception):
    pass


def update_document_status(
    conn: psycopg.Connection,
    document_id: str,
    file_path: str,
    status: str,
    raw_text: str | None = None,
    structured_data: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (id, file_path, status, raw_text, structured_data, error_message, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (id)
            DO UPDATE SET
                file_path = EXCLUDED.file_path,
                status = EXCLUDED.status,
                raw_text = EXCLUDED.raw_text,
                structured_data = EXCLUDED.structured_data,
                error_message = EXCLUDED.error_message,
                updated_at = EXCLUDED.updated_at
            """,
            (
                document_id,
                file_path,
                status,
                raw_text,
                json.dumps(structured_data) if structured_data is not None else None,
                error_message,
                datetime.now(timezone.utc),
            ),
        )


def perform_ocr(file_path: str) -> str:
    logger.info("OCR step started for %s", file_path)
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise OCRProcessingError(f"File not found: {file_path}")

    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".csv", ".json"}:
        text = path.read_bytes().decode("utf-8", errors="replace")
        if "\ufffd" in text:
            logger.warning("Invalid UTF-8 bytes were replaced while reading %s", file_path)
        logger.info("OCR placeholder read text file for %s", file_path)
        return text

    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore

        text = pytesseract.image_to_string(Image.open(path))
        logger.info("OCR completed via Tesseract for %s", file_path)
        return text
    except ModuleNotFoundError:
        logger.warning("pytesseract/Pillow not installed; using placeholder OCR result")
        return f"[OCR_PLACEHOLDER] extracted text from {file_path}"
    except Exception as exc:
        raise OCRProcessingError(f"OCR failed for {file_path}: {exc}") from exc


def convert_text_to_structured_json(raw_text: str) -> dict[str, Any]:
    logger.info("LLM structuring step started")
    if not raw_text.strip():
        raise LLMProcessingError("Raw text is empty")

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    words = raw_text.split()

    structured = {
        "summary": " ".join(words[: CONFIG.summary_word_limit]),
        "line_count": len(lines),
        "word_count": len(words),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "entities": [],
    }

    logger.info("LLM simulation completed")
    return structured


def process_message(payload: dict[str, Any], conn: psycopg.Connection) -> None:
    document_id = str(payload["document_id"])
    file_path = str(payload["file_path"])

    logger.info("Processing started for document_id=%s file_path=%s", document_id, file_path)
    update_document_status(conn, document_id, file_path, "processing")
    conn.commit()

    raw_text = perform_ocr(file_path)
    logger.info("OCR extraction completed for document_id=%s", document_id)

    structured_data = convert_text_to_structured_json(raw_text)
    logger.info("Structured JSON generation completed for document_id=%s", document_id)

    update_document_status(
        conn,
        document_id,
        file_path,
        "completed",
        raw_text=raw_text,
        structured_data=structured_data,
        error_message=None,
    )
    conn.commit()
    logger.info("Document stored and marked completed for document_id=%s", document_id)


def validate_payload(payload: dict[str, Any]) -> None:
    if "document_id" not in payload or "file_path" not in payload:
        raise ValueError("Message must contain document_id and file_path")
    payload.setdefault("retries", 0)


def parse_retry_count(payload: dict[str, Any]) -> int:
    try:
        return max(0, int(payload.get("retries", 0)))
    except (TypeError, ValueError):
        return 0


def consume_forever() -> None:
    redis_client = Redis(
        host=CONFIG.redis_host,
        port=CONFIG.redis_port,
        decode_responses=True,
        retry_on_timeout=True,
        health_check_interval=30,
    )
    ensure_schema()

    logger.info(
        "Worker started. Listening queue=%s failed_queue=%s",
        CONFIG.redis_queue_name,
        CONFIG.redis_failed_queue_name,
    )

    while True:
        logger.info("Waiting for queue message")
        queue_result = redis_client.brpop(
            CONFIG.redis_queue_name, timeout=CONFIG.redis_poll_timeout_seconds
        )
        if not queue_result:
            continue

        _, raw_message = queue_result
        logger.info("Message received from Redis queue")

        try:
            payload = json.loads(raw_message)
            if not isinstance(payload, dict):
                raise ValueError("Message payload must be a JSON object")
            validate_payload(payload)
        except Exception as exc:
            logger.exception("Invalid queue message, sending to failed queue: %s", exc)
            redis_client.lpush(
                CONFIG.redis_failed_queue_name,
                json.dumps({"message": raw_message, "error": f"invalid payload: {exc}"}),
            )
            continue

        retries = parse_retry_count(payload)

        try:
            with psycopg.connect(postgres_dsn()) as conn:
                process_message(payload, conn)
        except Exception as exc:
            logger.exception("Processing failed for document_id=%s", payload.get("document_id"))

            try:
                with psycopg.connect(postgres_dsn()) as conn:
                    document_id = str(payload.get("document_id", "unknown"))
                    file_path = str(payload.get("file_path", ""))
                    update_document_status(
                        conn,
                        document_id,
                        file_path,
                        "failed",
                        error_message=str(exc),
                    )
                    conn.commit()
            except Exception as status_exc:
                logger.exception("Failed to persist failure status: %s", status_exc)

            if retries < CONFIG.max_retries:
                payload["retries"] = retries + 1
                backoff_seconds = CONFIG.retry_backoff_seconds * (2**retries)
                logger.info(
                    "Requeueing message for retry attempt %s/%s after %.2f seconds",
                    payload["retries"],
                    CONFIG.max_retries,
                    backoff_seconds,
                )
                time.sleep(backoff_seconds)
                redis_client.lpush(CONFIG.redis_queue_name, json.dumps(payload))
            else:
                logger.error("Max retries exceeded; moving message to failed queue")
                redis_client.lpush(
                    CONFIG.redis_failed_queue_name,
                    json.dumps({"message": payload, "error": str(exc)}),
                )


def main() -> None:
    logger.info("Initializing worker service")
    try:
        consume_forever()
    except KeyboardInterrupt:
        logger.info("Worker service stopped")


if __name__ == "__main__":
    main()
