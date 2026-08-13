from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sso_provider: Mapped[str] = mapped_column(String(32), default="local")
    sso_client_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sso_client_secret: Mapped[str | None] = mapped_column(Text, nullable=True)
    sso_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    admin_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_domain: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    vector_namespace: Mapped[str] = mapped_column(String(128), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    users = relationship("User", back_populates="tenant")
