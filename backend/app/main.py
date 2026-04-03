from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Generator

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.config import get_settings
from .core.database import get_db, init_db
from .core.security import create_access_token, decode_token, hash_password, verify_password
from .models import AuditLog, Conversation, Message, User
from .schemas import ChatRequest, ChatResponse, ConversationSummary, MessageRead, Token, UploadResponse, UserCreate, UserLogin, UserRead
from .services.agent import EnterpriseCopilot
from .services.knowledge import KnowledgeBase

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

copilot = EnterpriseCopilot()
knowledge = KnowledgeBase()


def get_current_user_from_header(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    return get_current_user(db, authorization)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.post("/api/auth/register", response_model=UserRead)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    if db.scalar(select(User).where((User.username == payload.username) | (User.email == payload.email))):
        raise HTTPException(status_code=400, detail="Username or email already exists")
    user = User(
        username=payload.username,
        email=payload.email,
        full_name=payload.full_name,
        role=payload.role if payload.role in {"viewer", "analyst", "admin"} else "analyst",
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=Token)
def login(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.username == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(user.username, extra_claims={"role": user.role, "user_id": user.id})
    db.add(AuditLog(user_id=user.id, action="login", target="auth", detail="User signed in"))
    db.commit()
    return Token(access_token=token)


@app.get("/api/auth/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user_from_header)):
    return current_user


@app.get("/api/conversations", response_model=list[ConversationSummary])
def list_conversations(current_user: User = Depends(get_current_user_from_header), db: Session = Depends(get_db)):
    conversations = db.scalars(select(Conversation).where(Conversation.user_id == current_user.id).order_by(Conversation.updated_at.desc())).all()
    return conversations


@app.get("/api/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(conversation_id: int, current_user: User = Depends(get_current_user_from_header), db: Session = Depends(get_db)):
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return db.scalars(select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at)).all()


@app.post("/api/upload", response_model=UploadResponse)
def upload_file(file: UploadFile = File(...), current_user: User = Depends(get_current_user_from_header), db: Session = Depends(get_db)):
    upload_dir = settings.upload_path / str(current_user.id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / file.filename
    with target.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    chunks_indexed, document = knowledge.ingest_file(db, current_user.id, file.filename, file.content_type or "application/octet-stream", target)
    db.add(AuditLog(user_id=current_user.id, action="upload", target=file.filename, detail=f"Indexed {chunks_indexed} chunks"))
    db.commit()
    return UploadResponse(document_id=document.id, filename=document.filename, chunks_indexed=chunks_indexed)


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current_user: User = Depends(get_current_user_from_header), db: Session = Depends(get_db)):
    conversation = _get_or_create_conversation(db, current_user.id, payload.conversation_id, payload.message)
    user_message = Message(conversation_id=conversation.id, role="user", content=payload.message)
    db.add(user_message)
    response = copilot.answer(db, current_user.role, payload.message, conversation.id)
    db.add(Message(conversation_id=conversation.id, role="assistant", content=response.answer, citations_json=json.dumps([citation.model_dump() for citation in response.citations]), chart_json=json.dumps(response.chart.model_dump()) if response.chart else None))
    db.add(AuditLog(user_id=current_user.id, action="chat", target=conversation.title, detail=payload.message[:200]))
    db.commit()
    return response


@app.post("/api/chat/stream")
def chat_stream(payload: ChatRequest, current_user: User = Depends(get_current_user_from_header), db: Session = Depends(get_db)):
    conversation = _get_or_create_conversation(db, current_user.id, payload.conversation_id, payload.message)
    db.add(Message(conversation_id=conversation.id, role="user", content=payload.message))
    response = copilot.answer(db, current_user.role, payload.message, conversation.id)
    db.add(Message(conversation_id=conversation.id, role="assistant", content=response.answer, citations_json=json.dumps([citation.model_dump() for citation in response.citations]), chart_json=json.dumps(response.chart.model_dump()) if response.chart else None))
    db.commit()

    def event_stream() -> Generator[str, None, None]:
        for token in response.answer.split():
            yield f"data: {json.dumps({'type': 'token', 'value': token})}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'value': response.model_dump()})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.websocket("/api/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            payload = json.loads(await websocket.receive_text())
            message = payload.get("message", "")
            conversation_id = payload.get("conversation_id")
            db = next(get_db())
            try:
                current_user = db.scalar(select(User).where(User.username == payload.get("username", "analyst")))
                if not current_user:
                    current_user = db.scalar(select(User).where(User.username == "analyst"))
                response = copilot.answer(db, current_user.role if current_user else "analyst", message, conversation_id)
            finally:
                db.close()
            await websocket.send_text(json.dumps(response.model_dump(), default=str))
    except WebSocketDisconnect:
        return


def get_current_user(db: Session, token: str | None) -> User:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    try:
        raw_token = token.removeprefix("Bearer ").strip()
        payload = decode_token(raw_token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    username = payload.get("sub")
    user = db.scalar(select(User).where(User.username == username))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _get_or_create_conversation(db: Session, user_id: int, conversation_id: int | None, title_hint: str) -> Conversation:
    if conversation_id:
        conversation = db.get(Conversation, conversation_id)
        if not conversation or conversation.user_id != user_id:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation
    conversation = Conversation(user_id=user_id, title=title_hint[:60] or "New conversation")
    db.add(conversation)
    db.flush()
    return conversation
