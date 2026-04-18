from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentBase(BaseModel):
    file_name: str
    file_path: str
    status: str


class DocumentResponse(DocumentBase):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
