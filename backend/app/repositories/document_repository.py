from typing import List

from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, file_name: str, file_path: str, status: str) -> Document:
        document = Document(file_name=file_name, file_path=file_path, status=status)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_all(self) -> List[Document]:
        return self.db.query(Document).order_by(Document.created_at.desc()).all()
