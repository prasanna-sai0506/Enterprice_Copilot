import json
import time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth_middleware import get_current_user, token_from_request, user_from_token
from models.query_log import QueryLog
from models.tenant import Tenant
from models.user import User
from services.llm_service import build_system_prompt, chat_complete, classify, stream_tokens
from services.rag_service import query_knowledge_base
from services.roles import is_sensitive_query, scopes_for

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatBody(BaseModel):
    message: str
    access_token: str | None = None
    history: list | None = None


@router.post("")
async def chat(
    body: ChatBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = token_from_request(request) or body.access_token
    user = user_from_token(token)
    start = time.time()
    tenant = await db.scalar(
        select(Tenant).where(Tenant.tenant_id == user["tenant_id"], Tenant.is_active.is_(True))
    )
    db_user = await db.scalar(
        select(User).where(User.user_id == user["user_id"], User.tenant_id == user["tenant_id"])
    )
    if not tenant or not db_user:
        from fastapi import HTTPException

        raise HTTPException(401, "Session expired. Sign in again.")
    scopes = scopes_for(db_user.role, db_user.department)
    try:
        chunks = query_knowledge_base(
            body.message, tenant.vector_namespace, tenant.tenant_id, scopes, top_k=5
        )
    except Exception:
        chunks = []
    prompt = build_system_prompt(tenant, db_user, scopes, chunks)
    try:
        answer = chat_complete(body.message, chunks, prompt, tenant, body.history or [])
    except Exception as e:
        answer = f"I couldn't complete that answer just now. Please try again. ({e})"
    sources = [
        {"file": c.get("filename"), "page": c.get("page_number"), "chunk": (c.get("text") or "")[:180]}
        for c in chunks
    ]
    log = QueryLog(
        tenant_id=tenant.tenant_id,
        user_id=db_user.user_id,
        query_text=body.message,
        response_text=answer,
        sources_used=json.dumps(sources),
        is_sensitive=is_sensitive_query(body.message),
        latency_ms=int((time.time() - start) * 1000),
    )
    db.add(log)
    await db.commit()

    async def gen():
        async for piece in stream_tokens(answer):
            yield f"data: {json.dumps({'token': piece})}\n\n"
        yield f"data: {json.dumps({'done': True, 'sources': sources})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/history")
async def history(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(QueryLog)
            .where(QueryLog.tenant_id == user["tenant_id"], QueryLog.user_id == user["user_id"])
            .order_by(QueryLog.id.desc())
            .limit(50)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "query": r.query_text,
            "response": r.response_text,
            "sources": json.loads(r.sources_used or "[]"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "sensitive": r.is_sensitive,
        }
        for r in rows
    ]


@router.delete("/history/{log_id}")
async def delete_one(log_id: int, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(
        select(QueryLog).where(
            QueryLog.id == log_id,
            QueryLog.tenant_id == user["tenant_id"],
            QueryLog.user_id == user["user_id"],
        )
    )
    if not row:
        raise HTTPException(404, "Chat not found")
    await db.delete(row)
    await db.commit()
    return {"ok": True}


@router.delete("/history")
async def delete_all(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(QueryLog).where(QueryLog.tenant_id == user["tenant_id"], QueryLog.user_id == user["user_id"])
        )
    ).scalars().all()
    for r in rows:
        await db.delete(r)
    await db.commit()
    return {"ok": True, "deleted": len(rows)}
