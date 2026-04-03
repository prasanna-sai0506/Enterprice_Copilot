from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from docx import Document as DocxDocument
from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import DocumentChunk, DocumentFile


@dataclass
class SearchHit:
    source: str
    page: str
    excerpt: str
    score: float


class KnowledgeBase:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.storage_dir = self.settings.chroma_path

    def ingest_file(self, db: Session, user_id: int, filename: str, mime_type: str, file_path: Path) -> tuple[int, DocumentFile]:
        document = DocumentFile(user_id=user_id, filename=filename, mime_type=mime_type, storage_path=str(file_path), chunk_count=0)
        db.add(document)
        db.flush()

        text_blocks = self._extract_text(file_path, filename)
        chunks = self._chunk_text(text_blocks)
        chunk_models: list[DocumentChunk] = []
        for index, chunk in enumerate(chunks):
            chunk_models.append(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    source_name=filename,
                    page_label=str(chunk["page"]),
                    content=chunk["content"],
                )
            )
        db.add_all(chunk_models)
        document.chunk_count = len(chunk_models)
        db.commit()
        return len(chunk_models), document

    def search(self, db: Session, query: str, limit: int = 4) -> list[SearchHit]:
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        chunks = db.scalars(select(DocumentChunk).order_by(DocumentChunk.updated_at.desc())).all()
        scored: list[SearchHit] = []
        for chunk in chunks:
            score = self._score(query_terms, self._tokenize(chunk.content))
            if score <= 0:
                continue
            scored.append(SearchHit(source=chunk.source_name, page=chunk.page_label, excerpt=self._excerpt(chunk.content), score=score))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    def clear_user_data(self, db: Session, user_id: int) -> None:
        docs = db.scalars(select(DocumentFile).where(DocumentFile.user_id == user_id)).all()
        for document in docs:
            path = Path(document.storage_path)
            if path.exists():
                path.unlink()
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id.in_([document.id for document in docs])))
        db.execute(delete(DocumentFile).where(DocumentFile.user_id == user_id))
        db.commit()

    def get_document_chunks(self, db: Session, source_name: str) -> list[DocumentChunk]:
        return db.scalars(select(DocumentChunk).where(DocumentChunk.source_name == source_name).order_by(DocumentChunk.chunk_index)).all()

    def get_document_text(self, db: Session, source_name: str) -> str:
        chunks = self.get_document_chunks(db, source_name)
        return "\n".join(chunk.content for chunk in chunks)

    def _extract_text(self, file_path: Path, filename: str) -> list[dict[str, Any]]:
        suffix = file_path.suffix.lower()
        if suffix in {".txt", ".md"}:
            return [{"page": 1, "content": file_path.read_text(encoding="utf-8", errors="ignore")}]
        if suffix == ".csv":
            frame = pd.read_csv(file_path)
            return [{"page": 1, "content": frame.to_csv(index=False)}]
        if suffix == ".docx":
            doc = DocxDocument(file_path)
            return [{"page": index + 1, "content": paragraph.text} for index, paragraph in enumerate(doc.paragraphs) if paragraph.text.strip()]
        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            pages = []
            for index, page in enumerate(reader.pages):
                pages.append({"page": index + 1, "content": page.extract_text() or ""})
            return pages
        return [{"page": 1, "content": file_path.read_text(encoding="utf-8", errors="ignore")}]

    def _chunk_text(self, blocks: list[dict[str, Any]], chunk_size: int = 700, overlap: int = 120) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for block in blocks:
            content = block["content"].strip()
            if not content:
                continue
            start = 0
            while start < len(content):
                end = min(len(content), start + chunk_size)
                chunks.append({"page": block["page"], "content": content[start:end]})
                if end == len(content):
                    break
                start = max(end - overlap, start + 1)
        return chunks

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(token) > 2]

    def _score(self, query_terms: list[str], text_terms: list[str]) -> float:
        if not text_terms:
            return 0.0
        counts = {}
        for term in text_terms:
            counts[term] = counts.get(term, 0) + 1
        score = 0.0
        for term in query_terms:
            score += counts.get(term, 0)
        return score / max(len(text_terms), 1)

    def _excerpt(self, content: str, length: int = 220) -> str:
        cleaned = " ".join(content.split())
        return cleaned[:length] + ("..." if len(cleaned) > length else "")
