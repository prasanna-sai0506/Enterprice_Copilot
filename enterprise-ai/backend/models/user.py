import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_tenant_email"),)

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"))
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(64), default="employee")
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reports_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="users")
