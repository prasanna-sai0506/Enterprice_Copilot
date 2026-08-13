from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.auth_service import try_decode
from services.roles import scopes_for


def token_from_request(request: Request, x_access_token: str | None = None) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    for key in ("x-access-token", "x-auth-token"):
        val = request.headers.get(key)
        if val:
            return val.strip()
    if x_access_token:
        return x_access_token.strip()
    q = request.query_params.get("access_token")
    if q:
        return q.strip()
    return (request.cookies.get("access_token") or "").strip() or None


def user_from_token(token: str | None) -> dict:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = try_decode(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Sign in again.")
    if not payload.get("tenant_id"):
        raise HTTPException(status_code=403, detail="Wrong tenant")
    payload["allowed_scopes"] = payload.get("allowed_scopes") or scopes_for(
        payload.get("role"), payload.get("department")
    )
    return payload


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_access_token: str | None = Header(default=None),
) -> dict:
    payload = user_from_token(token_from_request(request, x_access_token))
    request.state.user = payload
    request.state.tenant_id = payload["tenant_id"]
    request.state.namespace = payload.get("vector_namespace")
    request.state.scopes = payload["allowed_scopes"]
    return payload


def require_roles(*roles):
    async def checker(user: dict = Depends(get_current_user)):
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return checker
