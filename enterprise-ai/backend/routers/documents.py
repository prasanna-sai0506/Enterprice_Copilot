import uuid
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import SessionLocal, get_db
from middleware.auth_middleware import get_current_user, require_roles
from models.document import Document
from models.ingest_job import IngestJob
from models.tenant import Tenant
from services.ingest_service import detect_type, ingest_document
from services.rag_service import delete_document_chunks
from services.roles import can_read_vault, can_write_vault, scopes_for, vaults_for

router = APIRouter(tags=["documents"])

ALLOWED_ROLES = {
    "ceo",
    "admin",
    "super_admin",
    "stakeholder",
    "manager",
    "hr",
    "hr_manager",
    "finance_head",
    "account_manager",
}


async def _run_ingest(job_id: str, file_bytes: bytes, filename: str, tenant_id: str, namespace: str, dept: str, access: str, user_id: str):
    async with SessionLocal() as db:
        job = await db.scalar(select(IngestJob).where(IngestJob.job_id == job_id, IngestJob.tenant_id == tenant_id))
        try:
            job.status = "processing"
            job.progress = 10
            await db.commit()
            doc_id, n = ingest_document(file_bytes, filename, tenant_id, namespace, dept, access)
            db.add(
                Document(
                    doc_id=doc_id,
                    tenant_id=tenant_id,
                    filename=filename,
                    file_type=detect_type(filename),
                    department=dept,
                    access_level=access,
                    chunk_count=n,
                    ingested_by=user_id,
                )
            )
            job.status = "done"
            job.progress = 100
            job.doc_id = doc_id
            job.message = f"Ingested {n} chunks"
            await db.commit()
        except Exception as e:
            job.status = "error"
            job.message = str(e)
            await db.commit()


@router.post("/documents/upload")
async def upload(
    background: BackgroundTasks,
    request: Request,
    file: UploadFile = File(...),
    department: str = Form("general"),
    access_level: str = Form("general"),
    access_token: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    from middleware.auth_middleware import token_from_request, user_from_token

    user = user_from_token(token_from_request(request) or access_token)
    access_level = (access_level or "general").lower()
    if not can_write_vault(user.get("role") or "employee", access_level):
        raise HTTPException(403, "You cannot upload into this vault")
    department = department or user.get("department") or "general"
    raw = await file.read()
    if len(raw) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, "File too large")
    try:
        detect_type(file.filename)
    except ValueError as e:
        raise HTTPException(400, str(e))
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == user["tenant_id"]))
    job = IngestJob(tenant_id=tenant.tenant_id, filename=file.filename, status="queued", progress=0)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    background.add_task(
        _run_ingest,
        job.job_id,
        raw,
        file.filename,
        tenant.tenant_id,
        tenant.vector_namespace,
        department,
        access_level,
        user["user_id"],
    )
    return {"job_id": job.job_id, "status": "queued"}


@router.get("/ingest/status/{job_id}")
async def ingest_status(job_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await db.scalar(
        select(IngestJob).where(IngestJob.job_id == job_id, IngestJob.tenant_id == user["tenant_id"])
    )
    if not job:
        raise HTTPException(404, "Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "doc_id": job.doc_id,
    }


@router.get("/documents/vaults")
async def list_vaults(user: dict = Depends(get_current_user)):
    return vaults_for(user.get("role") or "employee")


@router.get("/documents")
async def list_docs(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    vault: str | None = None,
):
    rows = (
        await db.execute(select(Document).where(Document.tenant_id == user["tenant_id"]).order_by(Document.ingested_at.desc()))
    ).scalars().all()
    role = user.get("role") or "employee"
    visible = []
    for d in rows:
        level = d.access_level or "general"
        if not can_read_vault(role, level) and level not in scopes_for(role, user.get("department")):
            continue
        if vault and level != vault:
            continue
        visible.append(
            {
                "doc_id": d.doc_id,
                "filename": d.filename,
                "file_type": d.file_type,
                "department": d.department,
                "access_level": level,
                "chunk_count": d.chunk_count,
                "ingested_at": d.ingested_at.isoformat() if d.ingested_at else None,
            }
        )
    return visible


@router.delete("/documents/{doc_id}")
async def delete_doc(
    doc_id: str,
    user: dict = Depends(require_roles("ceo", "admin", "super_admin", "hr")),
    db: AsyncSession = Depends(get_db),
):
    doc = await db.scalar(select(Document).where(Document.doc_id == doc_id, Document.tenant_id == user["tenant_id"]))
    if not doc:
        raise HTTPException(404, "Document not found")
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == user["tenant_id"]))
    delete_document_chunks(tenant.vector_namespace, tenant.tenant_id, doc_id)
    await db.delete(doc)
    await db.commit()
    return {"ok": True}
