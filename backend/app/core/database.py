from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_directories() -> None:
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)


def init_db() -> None:
    from .. import models  # noqa: F401

    ensure_directories()
    Base.metadata.create_all(bind=engine)
    seed_demo_data()


def seed_demo_data() -> None:
    from ..models import User, SalesRecord
    from .security import hash_password

    with SessionLocal() as db:
        if not db.scalar(select(User.id).limit(1)):
            demo_users = [
                User(username="analyst", email="analyst@demo.example", full_name="Avery Analyst", role="analyst", password_hash=hash_password("password123")),
                User(username="viewer", email="viewer@demo.example", full_name="Victor Viewer", role="viewer", password_hash=hash_password("password123")),
                User(username="admin", email="admin@demo.example", full_name="Ada Admin", role="admin", password_hash=hash_password("password123")),
            ]
            db.add_all(demo_users)
            db.commit()

        # Backfill older demo rows that used reserved .local domains.
        users_with_local = db.scalars(select(User).where(User.email.like("%@demo.local"))).all()
        if users_with_local:
            for user in users_with_local:
                user.email = user.email.replace("@demo.local", "@demo.example")
            db.commit()

        if not db.scalar(select(SalesRecord.id).limit(1)):
            sales_rows = [
                SalesRecord(period="2026-01", region="North", product="Core", revenue=124000, orders=430, profit=32100),
                SalesRecord(period="2026-01", region="South", product="Core", revenue=98000, orders=390, profit=25200),
                SalesRecord(period="2026-02", region="North", product="Core", revenue=131000, orders=452, profit=34400),
                SalesRecord(period="2026-02", region="South", product="Core", revenue=103000, orders=401, profit=27850),
                SalesRecord(period="2026-03", region="North", product="Core", revenue=116000, orders=411, profit=29150),
                SalesRecord(period="2026-03", region="South", product="Core", revenue=94000, orders=372, profit=23300),
                SalesRecord(period="2026-04", region="North", product="Core", revenue=138000, orders=469, profit=36550),
                SalesRecord(period="2026-04", region="South", product="Core", revenue=112000, orders=426, profit=30120),
                SalesRecord(period="2026-01", region="North", product="Premium", revenue=76000, orders=180, profit=21400),
                SalesRecord(period="2026-02", region="North", product="Premium", revenue=82000, orders=194, profit=22900),
                SalesRecord(period="2026-03", region="North", product="Premium", revenue=79000, orders=189, profit=22100),
                SalesRecord(period="2026-04", region="North", product="Premium", revenue=91000, orders=203, profit=25700),
            ]
            db.add_all(sales_rows)
            db.commit()
