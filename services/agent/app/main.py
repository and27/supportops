from __future__ import annotations

import json
import logging
import os
import uuid
from hashlib import sha256
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import requests
from supabase import Client, create_client

app = FastAPI()

logger = logging.getLogger("supportops.agent")
logging.basicConfig(level=logging.INFO, format="%(message)s")

_supabase: Client | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_event(level: int, event: str, **fields: Any) -> None:
    payload = {"ts": utc_now(), "event": event, **fields}
    logger.log(level, json.dumps(payload, ensure_ascii=True))


def get_supabase_client() -> Client:
    global _supabase
    if _supabase is not None:
        return _supabase

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set")

    _supabase = create_client(supabase_url, supabase_key)
    return _supabase


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    user_id: str | None = None
    channel: Literal["web"]
    message: str = Field(min_length=1)
    metadata: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    action: Literal["reply", "ask_clarifying", "create_ticket", "escalate"]
    confidence: float
    ticket_id: str | None = None
    citations: list[dict[str, str]] | None = None


class KBDocument(BaseModel):
    id: str
    title: str
    content: str
    tags: list[str]
    created_at: str | None = None
    updated_at: str | None = None


class KBCreate(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


class KBUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


class TicketResponse(BaseModel):
    id: str
    conversation_id: str | None = None
    status: str
    priority: str
    subject: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class IngestRequest(BaseModel):
    document_id: str
    chunk_size: int = 120
    chunk_overlap: int = 20
    force: bool = False


class IngestResponse(BaseModel):
    document_id: str
    chunks_total: int
    chunks_inserted: int
    chunks_skipped: int
    chunks_deleted: int
    embedding_model: str
    embedding_version: str | None = None


class EmbeddingProvider(Protocol):
    model: str
    version: str | None

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str, version: str | None = None) -> None:
        self.api_key = api_key
        self.model = model
        self.version = version

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        return [item["embedding"] for item in data]


def decide_response(message: str) -> tuple[str, str, float]:
    msg = message.strip().lower()
    if not msg:
        return (
            "Please share a bit more detail so I can help.",
            "ask_clarifying",
            0.2,
        )

    ticket_keywords = ("bug", "error", "issue", "incident", "crash", "outage", "fail")
    if any(keyword in msg for keyword in ticket_keywords):
        return (
            "Thanks for reporting this. I am creating a ticket and will follow up with next steps.",
            "create_ticket",
            0.35,
        )

    if len(msg.split()) < 4:
        return (
            "Can you add more context (account, steps, and expected behavior)?",
            "ask_clarifying",
            0.45,
        )

    return (
        "Thanks. I am checking our knowledge base. For now, try restarting the app and share any error code.",
        "reply",
        0.7,
    )


def normalize_tags(tags: list[str]) -> list[str]:
    normalized = []
    for tag in tags:
        clean = tag.strip().lower()
        if clean:
            normalized.append(clean)
    return sorted(set(normalized))


def extract_hash_tags(message: str) -> list[str]:
    tags = []
    for word in message.split():
        if word.startswith("#") and len(word) > 1:
            tags.append(word[1:])
    return normalize_tags(tags)


def retrieve_kb_candidates(
    supabase: Client, message: str, limit: int = 3
) -> list[dict[str, Any]]:
    query = message.strip().replace(",", " ")
    if not query:
        return []

    tags = extract_hash_tags(query)
    try:
        if tags:
            tagged = (
                supabase.table("kb_documents")
                .select("*")
                .contains("tags", [tags[0]])
                .limit(limit)
                .execute()
            )
            if tagged.data:
                return tagged.data

        text = (
            supabase.table("kb_documents")
            .select("*")
            .or_(f"title.ilike.%{query}%,content.ilike.%{query}%")
            .limit(limit)
            .execute()
        )
        return text.data or []
    except Exception as exc:
        log_event(logging.ERROR, "kb_retrieval_error", error=str(exc))
        return []


def build_kb_reply(document: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    title = document.get("title", "Knowledge Base")
    content = document.get("content", "")
    excerpt = content.strip().replace("\n", " ")
    if len(excerpt) > 360:
        excerpt = f"{excerpt[:360].rstrip()}..."
    reply = f"{title}: {excerpt}"
    citations = [{"kb_document_id": document.get("id", "")}]
    return reply, citations


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    size = max(1, min(chunk_size, 400))
    overlap = max(0, min(chunk_overlap, size - 1))

    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(0, end - overlap)
    return chunks


def hash_chunk(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def get_embedding_provider() -> EmbeddingProvider:
    provider_name = (os.getenv("EMBEDDING_PROVIDER") or "openai").lower()
    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        version = os.getenv("EMBEDDING_VERSION")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAIEmbeddingProvider(api_key=api_key, model=model, version=version)

    raise RuntimeError(f"Unsupported embedding provider: {provider_name}")


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    log_event(logging.WARNING, "http_error", status_code=exc.status_code, detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    log_event(logging.ERROR, "unhandled_error", error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "internal_error"})


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    conversation_id = payload.conversation_id or str(uuid.uuid4())
    client_host = request.client.host if request.client else "unknown"

    log_event(
        logging.INFO,
        "chat_request",
        conversation_id=conversation_id,
        user_id=payload.user_id,
        channel=payload.channel,
        client_ip=client_host,
    )

    try:
        if payload.conversation_id is None:
            supabase.table("conversations").insert(
                {
                    "id": conversation_id,
                    "user_id": payload.user_id,
                    "channel": payload.channel,
                    "metadata": payload.metadata,
                }
            ).execute()

        supabase.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "role": "user",
                "content": payload.message,
            }
        ).execute()

        kb_candidates = retrieve_kb_candidates(supabase, payload.message)
        citations = None
        if kb_candidates:
            reply, citations = build_kb_reply(kb_candidates[0])
            action = "reply"
            confidence = 0.85
        else:
            reply, action, confidence = decide_response(payload.message)
        ticket_id = None
        if action in ("create_ticket", "escalate"):
            ticket_result = supabase.table("tickets").insert(
                {
                    "conversation_id": conversation_id,
                    "subject": payload.message[:160],
                }
            ).execute()
            if ticket_result.data:
                ticket_id = ticket_result.data[0].get("id")
            if not ticket_id:
                raise RuntimeError("ticket_insert_failed")

        supabase.table("messages").insert(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": reply,
                "metadata": {"citations": citations} if citations else None,
            }
        ).execute()
    except Exception as exc:
        log_event(
            logging.ERROR,
            "db_error",
            conversation_id=conversation_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="db_error")

    log_event(
        logging.INFO,
        "chat_response",
        conversation_id=conversation_id,
        action=action,
        confidence=confidence,
        ticket_id=ticket_id,
        citations=citations,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        action=action,
        confidence=confidence,
        ticket_id=ticket_id,
        citations=citations,
    )


@app.get("/v1/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str) -> TicketResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    try:
        result = (
            supabase.table("tickets").select("*").eq("id", ticket_id).limit(1).execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", ticket_id=ticket_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="ticket_not_found")

    ticket = result.data[0]
    return TicketResponse(**ticket)


@app.get("/v1/tickets", response_model=list[TicketResponse])
async def list_tickets(limit: int = 50) -> list[TicketResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    safe_limit = max(1, min(limit, 100))
    try:
        result = (
            supabase.table("tickets")
            .select("*")
            .order("created_at", desc=True)
            .limit(safe_limit)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [TicketResponse(**ticket) for ticket in (result.data or [])]


@app.get("/v1/kb", response_model=list[KBDocument])
async def list_kb() -> list[KBDocument]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    try:
        result = (
            supabase.table("kb_documents")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [KBDocument(**doc) for doc in (result.data or [])]


@app.post("/v1/kb", response_model=KBDocument, status_code=201)
async def create_kb(payload: KBCreate) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    data = payload.model_dump()
    data["tags"] = normalize_tags(data.get("tags") or [])

    try:
        result = supabase.table("kb_documents").insert(data).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=500, detail="kb_create_failed")

    return KBDocument(**result.data[0])


@app.get("/v1/kb/{doc_id}", response_model=KBDocument)
async def get_kb(doc_id: str) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    try:
        result = (
            supabase.table("kb_documents").select("*").eq("id", doc_id).limit(1).execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    return KBDocument(**result.data[0])


@app.patch("/v1/kb/{doc_id}", response_model=KBDocument)
async def update_kb(doc_id: str, payload: KBUpdate) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    updates = payload.model_dump(exclude_unset=True)
    if "tags" in updates and updates["tags"] is not None:
        updates["tags"] = normalize_tags(updates["tags"])
    updates["updated_at"] = utc_now()

    try:
        result = (
            supabase.table("kb_documents")
            .update(updates)
            .eq("id", doc_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    return KBDocument(**result.data[0])


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest) -> IngestResponse:
    try:
        supabase = get_supabase_client()
        provider = get_embedding_provider()
    except RuntimeError as exc:
        log_event(logging.ERROR, "ingest_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="ingest_not_configured")

    try:
        doc_result = (
            supabase.table("kb_documents")
            .select("*")
            .eq("id", payload.document_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=payload.document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc_result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    document = doc_result.data[0]
    chunks = chunk_text(
        document.get("content", ""), payload.chunk_size, payload.chunk_overlap
    )
    if not chunks:
        raise HTTPException(status_code=400, detail="kb_content_empty")

    chunk_hashes = [hash_chunk(chunk) for chunk in chunks]
    unique_map: dict[str, int] = {}
    unique_chunks: list[str] = []
    for index, chunk_hash in enumerate(chunk_hashes):
        if chunk_hash in unique_map:
            continue
        unique_map[chunk_hash] = index
        unique_chunks.append(chunks[index])

    try:
        existing = (
            supabase.table("kb_chunks")
            .select("id,chunk_hash")
            .eq("document_id", payload.document_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=payload.document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    existing_hashes = {
        row.get("chunk_hash"): row.get("id")
        for row in (existing.data or [])
        if row.get("chunk_hash")
    }
    new_hashes = set(unique_map.keys())

    chunks_deleted = 0
    if not payload.force:
        to_delete = [row_id for chash, row_id in existing_hashes.items() if chash not in new_hashes]
    else:
        to_delete = [row_id for row_id in existing_hashes.values()]

    if to_delete:
        try:
            supabase.table("kb_chunks").delete().in_("id", to_delete).execute()
            chunks_deleted = len(to_delete)
        except Exception as exc:
            log_event(logging.ERROR, "db_error", doc_id=payload.document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    if payload.force:
        existing_hashes = {}

    to_insert_hashes = [chash for chash in unique_map.keys() if chash not in existing_hashes]
    to_insert_chunks = [chunks[unique_map[chash]] for chash in to_insert_hashes]

    chunks_inserted = 0
    if to_insert_chunks:
        try:
            embeddings = provider.embed(to_insert_chunks)
        except Exception as exc:
            log_event(logging.ERROR, "embedding_error", error=str(exc))
            raise HTTPException(status_code=500, detail="embedding_error")

        rows = []
        for chash, chunk, embedding in zip(to_insert_hashes, to_insert_chunks, embeddings):
            rows.append(
                {
                    "document_id": payload.document_id,
                    "chunk_index": unique_map[chash],
                    "content": chunk,
                    "chunk_hash": chash,
                    "embedding": embedding,
                    "embedding_model": provider.model,
                    "embedding_version": provider.version,
                }
            )
        try:
            supabase.table("kb_chunks").insert(rows).execute()
            chunks_inserted = len(rows)
        except Exception as exc:
            log_event(logging.ERROR, "db_error", doc_id=payload.document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    chunks_total = len(unique_chunks)
    chunks_skipped = chunks_total - chunks_inserted

    return IngestResponse(
        document_id=payload.document_id,
        chunks_total=chunks_total,
        chunks_inserted=chunks_inserted,
        chunks_skipped=chunks_skipped,
        chunks_deleted=chunks_deleted,
        embedding_model=provider.model,
        embedding_version=provider.version,
    )
