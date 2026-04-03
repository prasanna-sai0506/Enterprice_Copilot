from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    username: str
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)
    role: str = "analyst"


class UserLogin(BaseModel):
    username: str
    password: str


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class ChatRequest(BaseModel):
    conversation_id: int | None = None
    message: str


class Citation(BaseModel):
    source: str
    excerpt: str
    page: str | None = None


class ChartPayload(BaseModel):
    kind: str
    title: str
    spec: dict[str, Any]


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    citations: list[Citation] = []
    chart: ChartPayload | None = None
    tool_used: list[str] = []


class ConversationSummary(BaseModel):
    id: int
    title: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageRead(BaseModel):
    id: int
    role: str
    content: str
    citations_json: str | None = None
    chart_json: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UploadResponse(BaseModel):
    document_id: int
    filename: str
    chunks_indexed: int
