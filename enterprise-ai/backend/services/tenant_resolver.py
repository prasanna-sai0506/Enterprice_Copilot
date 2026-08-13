from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.tenant import Tenant


def subdomain_from_host(host: str | None) -> str | None:
    if not host:
        return None
    host = host.split(":")[0].lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return None
    # Preview / sandbox hosts are not tenant subdomains
    if any(x in host for x in ("e2b.app", "e2b.dev", "vercel.app", "onrender.com", "ngrok", "trycloudflare")):
        return None
    if host.endswith(".ent-ai.com") or host.endswith(".ent-ai.local"):
        return host.split(".")[0]
    return None


async def get_tenant_by_id(db: AsyncSession, tenant_id: str) -> Tenant:
    row = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id, Tenant.is_active.is_(True)))
    if not row:
        raise HTTPException(status_code=404, detail="Enterprise not registered")
    return row


async def resolve_tenant(request: Request, db: AsyncSession, explicit: str | None = None) -> Tenant:
    tid = explicit or request.query_params.get("tenant") or request.query_params.get("subdomain")
    if not tid:
        tid = subdomain_from_host(request.headers.get("host"))
    if not tid:
        tid = request.cookies.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=404, detail="Enterprise not registered")
    return await get_tenant_by_id(db, tid)
