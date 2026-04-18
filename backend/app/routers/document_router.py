from typing import List

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentResponse
from app.services.document_service import DocumentService
from app.services.storage_service import LocalStorageService

router = APIRouter(tags=["documents"])


def get_document_service(db: Session = Depends(get_db)) -> DocumentService:
    settings = get_settings()
    repository = DocumentRepository(db)
    storage = LocalStorageService(
        upload_dir=settings.local_upload_dir,
        max_upload_size_mb=settings.max_upload_size_mb,
    )
    return DocumentService(repository=repository, storage_service=storage)


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
):
    return await service.upload_document(file)


@router.get("/documents", response_model=List[DocumentResponse])
def list_documents(service: DocumentService = Depends(get_document_service)):
    return service.list_documents()
