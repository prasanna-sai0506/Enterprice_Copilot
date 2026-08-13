from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session


async def ensure_columns():
    """Add columns on existing SQLite files without wiping data."""
    from sqlalchemy import text

    stmts = [
        "ALTER TABLE tenants ADD COLUMN email_domain VARCHAR(255)",
        "ALTER TABLE tenants ADD COLUMN owner_user_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN reports_to VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN status VARCHAR(32) DEFAULT 'active'",
    ]
    async with engine.begin() as conn:
        for s in stmts:
            try:
                await conn.execute(text(s))
            except Exception:
                pass
