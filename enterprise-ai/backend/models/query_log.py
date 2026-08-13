import uuid
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class QueryLog(Base):
    __tablename__ = "query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    sources_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
