import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"))
    filename: Mapped[str] = mapped_column(String(255))
    file_type: Mapped[str] = mapped_column(String(16))
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    access_level: Mapped[str] = mapped_column(String(32), default="general")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ingested_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.user_id"), nullable=True)
