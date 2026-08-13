import uuid
from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class IngestJob(Base):
    __tablename__ = "ingest_jobs"

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    doc_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
