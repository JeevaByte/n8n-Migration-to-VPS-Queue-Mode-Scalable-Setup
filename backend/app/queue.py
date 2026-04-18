import hashlib
import json
import logging
import time
from typing import Any

from redis import Redis
from redis.exceptions import RedisError


LOGGER = logging.getLogger(__name__)

_DEDUPED_PUBLISH_LUA = """
if redis.call("SET", KEYS[1], ARGV[1], "NX", "EX", ARGV[2]) then
  redis.call("RPUSH", KEYS[2], ARGV[3])
  return 1
else
  return 0
end
"""


class QueuePublisher:
    def __init__(
        self,
        redis_client: Redis,
        queue_name: str,
        max_retries: int,
        retry_backoff_seconds: float,
        dedupe_ttl_seconds: int,
    ) -> None:
        self.redis_client = redis_client
        self.queue_name = queue_name
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.dedupe_ttl_seconds = dedupe_ttl_seconds

    def _payload(self, document_id: str, file_path: str) -> str:
        return json.dumps(
            {"document_id": document_id, "file_path": file_path},
            separators=(",", ":"),
            sort_keys=True,
        )

    def _dedupe_key(self, document_id: str, file_path: str) -> str:
        digest = hashlib.sha256(file_path.encode("utf-8")).hexdigest()
        return f"upload-event:{document_id}:{digest}"

    def publish_upload_event(self, document_id: str, file_path: str) -> bool:
        payload = self._payload(document_id, file_path)
        dedupe_key = self._dedupe_key(document_id, file_path)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                published = self.redis_client.eval(
                    _DEDUPED_PUBLISH_LUA,
                    2,
                    dedupe_key,
                    self.queue_name,
                    "1",
                    str(self.dedupe_ttl_seconds),
                    payload,
                )
                if published == 1:
                    LOGGER.info(
                        "Queue publish success",
                        extra={
                            "event": "queue_publish_success",
                            "queue": self.queue_name,
                            "document_id": document_id,
                            "file_path": file_path,
                            "attempt": attempt,
                        },
                    )
                    return True

                LOGGER.info(
                    "Queue publish deduplicated",
                    extra={
                        "event": "queue_publish_deduplicated",
                        "queue": self.queue_name,
                        "document_id": document_id,
                        "file_path": file_path,
                    },
                )
                return False
            except RedisError as exc:
                last_error = exc
                LOGGER.warning(
                    "Queue publish retry",
                    extra={
                        "event": "queue_publish_retry",
                        "queue": self.queue_name,
                        "document_id": document_id,
                        "file_path": file_path,
                        "attempt": attempt,
                        "max_retries": self.max_retries,
                        "error": str(exc),
                    },
                )
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds * attempt)

        LOGGER.error(
            "Queue publish failed",
            extra={
                "event": "queue_publish_failed",
                "queue": self.queue_name,
                "document_id": document_id,
                "file_path": file_path,
                "error": str(last_error) if last_error else "unknown",
            },
        )
        if last_error:
            raise last_error
        raise RuntimeError("Queue publish failed without a captured Redis error")
