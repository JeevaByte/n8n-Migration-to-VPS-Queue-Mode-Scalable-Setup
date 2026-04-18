from datetime import datetime

from pydantic import BaseModel


class DocumentBase(BaseModel):
    file_name: str
    file_path: str
    status: str


class DocumentResponse(DocumentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
