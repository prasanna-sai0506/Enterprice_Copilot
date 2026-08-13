import os
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import Base, engine, get_db
from models.tenant import Tenant
from routers import admin, auth, chat, documents
from seed import seed_if_needed
from services.tenant_resolver import subdomain_from_host

BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Enterprise AI", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(admin.router)

static_dir = BASE / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def startup():
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    from database import ensure_columns

    await ensure_columns()
    from database import SessionLocal

    async with SessionLocal() as db:
        await seed_if_needed(db)


@app.get("/tenant/info")
async def tenant_info():
    # Never disclose registered organizations.
    return {"product": "Enterprise AI", "branding": "Welcome to your enterprise-specific AI"}


@app.get("/health")
async def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
@app.get("/chat", response_class=HTMLResponse)
@app.get("/admin-ui", response_class=HTMLResponse)
@app.get("/library", response_class=HTMLResponse)
async def spa(request: Request):
    resp = templates.TemplateResponse("app.html", {"request": request})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp
