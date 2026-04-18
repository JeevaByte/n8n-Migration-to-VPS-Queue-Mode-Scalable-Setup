import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile, status


class LocalStorageService:
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf", ".webp"}

    def __init__(self, upload_dir: str, max_upload_size_mb: int):
        self.upload_dir = Path(upload_dir)
        self.max_upload_size_bytes = max_upload_size_mb * 1024 * 1024
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_.-]", "_", filename)
        return clean or f"file_{uuid.uuid4().hex}"

    def _validate(self, file: UploadFile) -> str:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File name is required.",
            )

        extension = os.path.splitext(file.filename)[1].lower()
        if extension not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file type. Allowed: jpg, jpeg, png, webp, pdf.",
            )
        return file.filename

    async def save_file(self, file: UploadFile) -> str:
        validated_filename = self._validate(file)

        safe_name = self._sanitize_filename(validated_filename)
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        destination = self.upload_dir / unique_name

        total_size = 0
        with destination.open("wb") as target:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break

                total_size += len(chunk)
                if total_size > self.max_upload_size_bytes:
                    destination.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="File too large.",
                    )
                target.write(chunk)
        return str(destination)
