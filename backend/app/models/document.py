from sqlalchemy import Column, DateTime, Integer, String, func

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String(512), nullable=False)
    file_path = Column(String(1024), nullable=False)
    status = Column(String(64), nullable=False, default="uploaded")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
