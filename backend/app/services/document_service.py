import logging
from typing import List

from fastapi import UploadFile

from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.storage_service import LocalStorageService

logger = logging.getLogger(__name__)


class DocumentService:
    def __init__(
        self,
        repository: DocumentRepository,
        storage_service: LocalStorageService,
    ):
        self.repository = repository
        self.storage_service = storage_service

    async def upload_document(self, file: UploadFile) -> DocumentResponse:
        logger.info("Uploading file: %s", file.filename)
        saved_path = await self.storage_service.save_file(file)

        document = self.repository.create(
            file_name=file.filename,
            file_path=saved_path,
            status="uploaded",
        )
        logger.info("Uploaded file saved with id=%s", document.id)
        return DocumentResponse.model_validate(document)

    def list_documents(self) -> List[DocumentResponse]:
        documents = self.repository.list_all()
        return [DocumentResponse.model_validate(doc) for doc in documents]
