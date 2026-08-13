from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.tenant import Tenant
from models.user import User
from middleware.auth_middleware import get_current_user
from services.auth_service import create_token, hash_password, verify_password
from services.domain import email_domain, is_public_email, slug_from_domain
from services.roles import scopes_for
from services.tenant_resolver import get_tenant_by_id

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class RegisterOrgBody(BaseModel):
    company_name: str
    name: str
    email: EmailStr
    password: str
    role: str = "ceo"


class JoinBody(BaseModel):
    name: str
    email: EmailStr
    password: str
    requested_role: str = "employee"
    department: str | None = None


def _token_for(user: User, tenant: Tenant) -> str:
    return create_token(
        {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "department": user.department,
            "tenant_id": tenant.tenant_id,
            "company_name": tenant.company_name,
            "vector_namespace": tenant.vector_namespace,
            "allowed_scopes": scopes_for(user.role, user.department),
        }
    )


def _auth_response(token: str, user: User, tenant: Tenant) -> JSONResponse:
    resp = JSONResponse({"access_token": token, "token_type": "bearer", "user": _user_payload(user, tenant)})
    for name, http_only in (("access_token", True), ("ea_token", False)):
        resp.set_cookie(
            name,
            token,
            httponly=http_only,
            samesite="none",
            secure=True,
            max_age=8 * 3600,
            path="/",
        )
    return resp


def _user_payload(user: User, tenant: Tenant) -> dict:
    return {
        "name": user.name,
        "email": user.email,
        "role": user.role,
        "department": user.department,
        "tenant_id": tenant.tenant_id,
        "company_name": tenant.company_name,
        "status": getattr(user, "status", "active"),
    }


async def _tenant_by_email(db: AsyncSession, email: str) -> Tenant | None:
    domain = email_domain(email)
    return await db.scalar(select(Tenant).where(Tenant.email_domain == domain, Tenant.is_active.is_(True)))


@router.post("/login")
async def login(body: LoginBody, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    tenant = await _tenant_by_email(db, email)
    if not tenant:
        # never reveal whether another org exists — only this domain
        raise HTTPException(
            status_code=401,
            detail="No workspace for this work email. Register your organization if you are the owner.",
        )
    user = await db.scalar(select(User).where(User.tenant_id == tenant.tenant_id, User.email == email))
    if not user or not verify_password(body.password, user.hashed_password or ""):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active or getattr(user, "status", "active") == "pending":
        raise HTTPException(status_code=403, detail="Your access is pending approval from your organization owner.")
    user.last_login = datetime.utcnow()
    await db.commit()
    return _auth_response(_token_for(user, tenant), user, tenant)


@router.post("/register-org")
async def register_org(body: RegisterOrgBody, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    if is_public_email(email):
        raise HTTPException(400, "Use a company or university email, not a personal mailbox.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    domain = email_domain(email)
    existing = await db.scalar(select(Tenant).where(Tenant.email_domain == domain))
    if existing:
        # Domain already owned — treat as join request. Never return the org name.
        exists = await db.scalar(select(User).where(User.tenant_id == existing.tenant_id, User.email == email))
        if exists:
            raise HTTPException(409, "An account with this email already exists. Sign in instead.")
        wanted = body.role if body.role in {"employee", "manager", "hr", "stakeholder"} else "employee"
        db.add(
            User(
                tenant_id=existing.tenant_id,
                email=email,
                name=body.name.strip(),
                hashed_password=hash_password(body.password),
                role=wanted,
                department=None,
                status="pending",
                is_active=False,
            )
        )
        await db.commit()
        return JSONResponse(
            {
                "pending": True,
                "message": "This work domain already has an owner. Your access request was sent. You will not see the organization until a CEO, HR, or manager approves you.",
            }
        )
    slug = slug_from_domain(domain)
    # unique tenant_id if slug taken
    base = slug
    n = 1
    while await db.scalar(select(Tenant).where(Tenant.tenant_id == slug)):
        n += 1
        slug = f"{base}{n}"
    tenant = Tenant(
        tenant_id=slug,
        company_name=body.company_name.strip(),
        subdomain=slug,
        email_domain=domain,
        support_email=email,
        admin_email=email,
        vector_namespace=f"ns_{slug}",
        sso_provider="local",
        is_active=True,
    )
    db.add(tenant)
    await db.flush()
    owner = User(
        tenant_id=tenant.tenant_id,
        email=email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
        role="ceo",
        department="Executive",
        status="active",
        is_active=True,
    )
    db.add(owner)
    await db.flush()
    tenant.owner_user_id = owner.user_id
    await db.commit()
    return _auth_response(_token_for(owner, tenant), owner, tenant)


@router.post("/join")
async def join_request(body: JoinBody, db: AsyncSession = Depends(get_db)):
    email = body.email.lower()
    if is_public_email(email):
        raise HTTPException(400, "Use your organization email.")
    tenant = await _tenant_by_email(db, email)
    if not tenant:
        raise HTTPException(404, "No workspace for this email domain. The owner must register the organization first.")
    exists = await db.scalar(select(User).where(User.tenant_id == tenant.tenant_id, User.email == email))
    if exists:
        raise HTTPException(409, "An account with this email already exists. Sign in or wait for approval.")
    role = body.requested_role if body.requested_role in {"employee", "manager", "hr", "stakeholder"} else "employee"
    user = User(
        tenant_id=tenant.tenant_id,
        email=email,
        name=body.name.strip(),
        hashed_password=hash_password(body.password),
        role=role,
        department=body.department,
        status="pending",
        is_active=False,
    )
    db.add(user)
    await db.commit()
    return {"ok": True, "message": "Request sent. Your CEO or HR will approve access. Organization name is never shown until you are approved."}


@router.post("/refresh")
async def refresh(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    tenant = await get_tenant_by_id(db, user["tenant_id"])
    db_user = await db.scalar(select(User).where(User.user_id == user["user_id"], User.tenant_id == tenant.tenant_id))
    if not db_user:
        raise HTTPException(401, "User not found")
    return {"access_token": _token_for(db_user, tenant), "token_type": "bearer"}


@router.post("/logout")
async def logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("access_token")
    return resp
