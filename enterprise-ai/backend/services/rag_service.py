"""RAG retrieve: tenant-isolated vector search + keyword boost.

Flow
----
Question
  -> embed (same MiniLM model used at ingest)
  -> Chroma query inside THIS tenant namespace only
  -> filter access_level to the caller's scopes (employees always get 'general')
  -> keyword overlap re-rank so policy terms like 'leave' win
  -> top_k chunks become LLM context
"""

import os
import re
from threading import Lock

import chromadb
from chromadb.utils import embedding_functions

from config import settings

_lock = Lock()
_client = None
_embed = None

STOP = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "for",
    "and", "or", "on", "at", "we", "our", "do", "does", "what", "how", "many",
}


def _get_client():
    global _client, _embed
    with _lock:
        if _client is None:
            os.makedirs(settings.CHROMA_PERSIST_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
            _embed = embedding_functions.DefaultEmbeddingFunction()
        return _client, _embed


def collection_for(namespace: str):
    client, embed = _get_client()
    return client.get_or_create_collection(name=namespace, embedding_function=embed)


def add_chunks(namespace: str, ids: list, documents: list, metadatas: list):
    col = collection_for(namespace)
    # Chroma add in batches
    batch = 100
    for i in range(0, len(ids), batch):
        col.add(
            ids=ids[i : i + batch],
            documents=documents[i : i + batch],
            metadatas=metadatas[i : i + batch],
        )


def delete_document_chunks(namespace: str, tenant_id: str, doc_id: str):
    col = collection_for(namespace)
    col.delete(where={"$and": [{"tenant_id": tenant_id}, {"doc_id": doc_id}]})


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if w not in STOP and len(w) > 2}


def _keyword_score(question: str, chunk: str) -> float:
    q, c = _tokens(question), _tokens(chunk)
    if not q:
        return 0.0
    return len(q & c) / len(q)


def query_knowledge_base(question: str, namespace: str, tenant_id: str, scopes: list[str], top_k: int = 6):
    col = collection_for(namespace)
    allowed = list({*(scopes or []), "general"})  # every employee always sees company-wide docs
    fetch = max(top_k * 4, 12)
    where = {
        "$and": [
            {"tenant_id": tenant_id},
            {"access_level": {"$in": allowed}},
        ]
    }
    try:
        res = col.query(query_texts=[question], n_results=fetch, where=where)
    except Exception:
        try:
            res = col.query(query_texts=[question], n_results=fetch, where={"tenant_id": tenant_id})
        except Exception:
            return []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    ranked = []
    for i, text in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        if meta.get("tenant_id") != tenant_id:
            continue
        level = meta.get("access_level") or "general"
        if level not in allowed:
            continue
        dist = dists[i] if i < len(dists) else 1.0
        vec = 1.0 / (1.0 + float(dist if dist is not None else 1.0))
        kw = _keyword_score(question, text)
        score = 0.65 * vec + 0.35 * kw
        ranked.append(
            {
                "text": text,
                "filename": meta.get("filename"),
                "page_number": meta.get("page_number"),
                "department": meta.get("department"),
                "access_level": level,
                "doc_id": meta.get("doc_id"),
                "heading": meta.get("heading"),
                "distance": dist,
                "score": score,
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    # de-duplicate near-identical chunks
    seen, out = set(), []
    for c in ranked:
        key = (c.get("filename"), (c.get("text") or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= top_k:
            break
    return out
