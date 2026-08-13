import csv
import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth_middleware import get_current_user, require_roles
from models.document import Document
from models.query_log import QueryLog
from models.tenant import Tenant
from models.user import User
from services.auth_service import hash_password
from services.roles import MANAGE_USERS_ROLES, can_manage, rank

router = APIRouter(prefix="/admin", tags=["admin"])


class TenantIn(BaseModel):
    tenant_id: str
    company_name: str
    subdomain: str
    support_email: str | None = None
    admin_email: str | None = None
    sso_provider: str = "local"


class UserIn(BaseModel):
    email: EmailStr
    name: str
    password: str | None = None
    role: str = "employee"
    department: str | None = None
    tenant_id: str | None = None


class UserPatch(BaseModel):
    role: str | None = None
    department: str | None = None
    is_active: bool | None = None
    name: str | None = None
    status: str | None = None
    reports_to: str | None = None


def _can_admin_people(user: dict):
    if user.get("role") not in MANAGE_USERS_ROLES:
        raise HTTPException(403, "Not allowed to manage people")
    return user


def _super(user: dict, x_admin_key: str | None):
    if user.get("role") != "super_admin":
        raise HTTPException(403, "super_admin only")
    if x_admin_key != settings.SUPER_ADMIN_API_KEY:
        raise HTTPException(403, "Invalid super admin API key")


@router.post("/tenants")
async def create_tenant(
    body: TenantIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_admin_key: str | None = Header(default=None),
):
    _super(user, x_admin_key)
    exists = await db.scalar(select(Tenant).where(Tenant.tenant_id == body.tenant_id))
    if exists:
        raise HTTPException(400, "Tenant exists")
    t = Tenant(
        tenant_id=body.tenant_id,
        company_name=body.company_name,
        subdomain=body.subdomain,
        support_email=body.support_email,
        admin_email=body.admin_email,
        sso_provider=body.sso_provider,
        vector_namespace=f"ns_{body.tenant_id}",
        is_active=True,
    )
    db.add(t)
    await db.commit()
    return {"tenant_id": t.tenant_id, "namespace": t.vector_namespace}


@router.get("/tenants")
async def list_tenants(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_admin_key: str | None = Header(default=None),
):
    _super(user, x_admin_key)
    rows = (await db.execute(select(Tenant))).scalars().all()
    return [
        {
            "tenant_id": t.tenant_id,
            "company_name": t.company_name,
            "subdomain": t.subdomain,
            "is_active": t.is_active,
            "namespace": t.vector_namespace,
        }
        for t in rows
    ]


@router.patch("/tenants/{tid}")
async def patch_tenant(
    tid: str,
    body: TenantIn,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_admin_key: str | None = Header(default=None),
):
    _super(user, x_admin_key)
    t = await db.scalar(select(Tenant).where(Tenant.tenant_id == tid))
    if not t:
        raise HTTPException(404)
    t.company_name = body.company_name
    t.subdomain = body.subdomain
    t.support_email = body.support_email
    t.admin_email = body.admin_email
    t.sso_provider = body.sso_provider
    await db.commit()
    return {"ok": True}


@router.post("/users")
async def create_user(body: UserIn, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _can_admin_people(user)
    if not can_manage(user["role"], body.role):
        raise HTTPException(403, "You cannot create a user at this level")
    tid = user["tenant_id"] if user["role"] != "super_admin" else (body.tenant_id or user["tenant_id"])
    exists = await db.scalar(select(User).where(User.tenant_id == tid, User.email == body.email.lower()))
    if exists:
        raise HTTPException(400, "User exists")
    u = User(
        tenant_id=tid,
        email=body.email.lower(),
        name=body.name,
        hashed_password=hash_password(body.password or "Password@123"),
        role=body.role,
        department=body.department,
        reports_to=user["user_id"] if user["role"] == "manager" else None,
        status="active",
        is_active=True,
    )
    db.add(u)
    await db.commit()
    return {"user_id": u.user_id}


@router.post("/users/import")
async def import_users(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _can_admin_people(user)
    text = (await file.read()).decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    created = 0
    for row in reader:
        email = (row.get("email") or "").strip().lower()
        if not email:
            continue
        exists = await db.scalar(select(User).where(User.tenant_id == user["tenant_id"], User.email == email))
        if exists:
            continue
        db.add(
            User(
                tenant_id=user["tenant_id"],
                email=email,
                name=row.get("name") or email,
                hashed_password=hash_password(row.get("password") or "Password@123"),
                role=row.get("role") or "employee",
                department=row.get("department"),
                is_active=True,
            )
        )
        created += 1
    await db.commit()
    return {"created": created}


@router.get("/users")
async def list_users(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _can_admin_people(user)
    rows = (await db.execute(select(User).where(User.tenant_id == user["tenant_id"]))).scalars().all()
    visible = []
    for u in rows:
        if user["role"] == "manager":
            same_team = u.reports_to == user["user_id"] or u.user_id == user["user_id"]
            same_dept = (u.department or "") == (user.get("department") or "") and rank(u.role) < rank("manager")
            if not (same_team or same_dept):
                continue
        visible.append(u)
    return [
        {
            "user_id": u.user_id,
            "email": u.email,
            "name": u.name,
            "role": u.role,
            "department": u.department,
            "is_active": u.is_active,
            "status": getattr(u, "status", "active"),
            "reports_to": getattr(u, "reports_to", None),
            "last_login": u.last_login.isoformat() if u.last_login else None,
        }
        for u in visible
    ]


@router.patch("/users/{uid}")
async def patch_user(uid: str, body: UserPatch, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _can_admin_people(user)
    u = await db.scalar(select(User).where(User.user_id == uid, User.tenant_id == user["tenant_id"]))
    if not u:
        raise HTTPException(404)
    if uid != user["user_id"] and not can_manage(user["role"], u.role):
        raise HTTPException(403, "You can only manage people below you")
    if body.role is not None:
        if not can_manage(user["role"], body.role):
            raise HTTPException(403, "Cannot assign that role")
        u.role = body.role
    if body.department is not None:
        u.department = body.department
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.status is not None:
        u.status = body.status
        if body.status == "active":
            u.is_active = True
    if body.name is not None:
        u.name = body.name
    if body.reports_to is not None:
        u.reports_to = body.reports_to
    await db.commit()
    return {"ok": True}


@router.delete("/users/{uid}")
async def deactivate_user(uid: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _can_admin_people(user)
    u = await db.scalar(select(User).where(User.user_id == uid, User.tenant_id == user["tenant_id"]))
    if not u:
        raise HTTPException(404)
    u.is_active = False
    await db.commit()
    return {"ok": True}


@router.get("/logs")
async def logs(user: dict = Depends(require_roles("ceo", "admin", "super_admin", "hr", "stakeholder")), db: AsyncSession = Depends(get_db), sensitive: bool = False):
    q = select(QueryLog).where(QueryLog.tenant_id == user["tenant_id"]).order_by(QueryLog.id.desc()).limit(200)
    if sensitive:
        q = q.where(QueryLog.is_sensitive.is_(True))
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "query": (r.query_text or "")[:160],
            "sensitive": r.is_sensitive,
            "latency_ms": r.latency_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.get("/stats")
async def stats(user: dict = Depends(require_roles("admin", "super_admin", "manager")), db: AsyncSession = Depends(get_db)):
    tid = user["tenant_id"]
    month_ago = datetime.utcnow() - timedelta(days=30)
    total = await db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.tenant_id == tid, QueryLog.created_at >= month_ago))
    users_n = await db.scalar(select(func.count()).select_from(User).where(User.tenant_id == tid, User.is_active.is_(True)))
    avg_lat = await db.scalar(select(func.avg(QueryLog.latency_ms)).where(QueryLog.tenant_id == tid))
    docs = await db.scalar(select(func.count()).select_from(Document).where(Document.tenant_id == tid))
    return {
        "queries_30d": total or 0,
        "active_users": users_n or 0,
        "avg_latency_ms": int(avg_lat or 0),
        "documents": docs or 0,
    }
