from __future__ import annotations

import json
import logging
import os
import re
import uuid
from hashlib import sha256
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import requests
import jwt
from jwt import InvalidTokenError
from dotenv import load_dotenv
from supabase import Client, create_client

agent_root = Path(__file__).resolve().parents[1]
load_dotenv(agent_root / ".env", override=False)
load_dotenv(agent_root / ".env.local", override=True)

app = FastAPI()

logger = logging.getLogger("supportops.agent")
logging.basicConfig(level=logging.INFO, format="%(message)s")

_supabase: Client | None = None
_default_org_id: str | None = None


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


def auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "false").lower() == "true"


def get_auth_user(request: Request) -> str | None:
    if not auth_enabled():
        return None
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="auth_required")
    token = auth_header.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="auth_required")
    secret = os.getenv("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=500, detail="auth_not_configured")
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid_token")
    return user_id


def load_memberships(supabase: Client, user_id: str) -> list[dict[str, Any]]:
    try:
        result = (
            supabase.table("members")
            .select("org_id, role")
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc), user_id=user_id)
        raise HTTPException(status_code=500, detail="db_error")
    return result.data or []


def get_member_role(supabase: Client, org_id: str, user_id: str) -> str:
    memberships = load_memberships(supabase, user_id)
    for membership in memberships:
        if membership.get("org_id") == org_id:
            return membership.get("role") or "viewer"
    raise HTTPException(status_code=403, detail="org_forbidden")


def ensure_write_access(
    request: Request,
    supabase: Client,
    org_id: str,
    user_id: str | None,
) -> None:
    if auth_enabled():
        if not user_id:
            raise HTTPException(status_code=401, detail="auth_required")
        role = get_member_role(supabase, org_id, user_id)
        if role == "viewer":
            raise HTTPException(status_code=403, detail="forbidden")
        return
    role = request.headers.get("x-org-role", "").lower()
    if role == "viewer":
        raise HTTPException(status_code=403, detail="forbidden")


def ensure_admin_access(supabase: Client, org_id: str, user_id: str | None) -> None:
    if not auth_enabled():
        return
    if not user_id:
        raise HTTPException(status_code=401, detail="auth_required")
    role = get_member_role(supabase, org_id, user_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="forbidden")


def get_default_org_id(supabase: Client) -> str:
    global _default_org_id
    if _default_org_id:
        return _default_org_id
    slug = os.getenv("DEFAULT_ORG_SLUG", "default")
    try:
        result = (
            supabase.table("orgs").select("id").eq("slug", slug).limit(1).execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc), org_slug=slug)
        raise HTTPException(status_code=500, detail="db_error")
    if not result.data:
        log_event(logging.ERROR, "default_org_missing", org_slug=slug)
        raise HTTPException(status_code=500, detail="default_org_missing")
    _default_org_id = result.data[0]["id"]
    return _default_org_id


def resolve_org_id(
    supabase: Client,
    request: Request | None = None,
    payload_org_id: str | None = None,
    user_id: str | None = None,
) -> str:
    org_id = payload_org_id
    if request is not None:
        org_id = org_id or request.headers.get("x-org-id")
        org_id = org_id or request.query_params.get("org_id")
    if auth_enabled():
        if not user_id:
            raise HTTPException(status_code=401, detail="auth_required")
        memberships = load_memberships(supabase, user_id)
        org_ids = [member.get("org_id") for member in memberships if member.get("org_id")]
        if not org_ids:
            raise HTTPException(status_code=403, detail="org_forbidden")
        if org_id:
            if org_id not in org_ids:
                raise HTTPException(status_code=403, detail="org_forbidden")
            return org_id
        if len(org_ids) == 1:
            return org_ids[0]
        raise HTTPException(status_code=400, detail="org_required")
    if org_id:
        return org_id
    return get_default_org_id(supabase)


def resolve_org_context(
    supabase: Client,
    request: Request,
    payload_org_id: str | None = None,
) -> tuple[str, str | None]:
    user_id = get_auth_user(request)
    org_id = resolve_org_id(supabase, request, payload_org_id, user_id)
    return org_id, user_id


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    user_id: str | None = None
    org_id: str | None = None
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
    org_id: str | None = None
    title: str
    content: str
    tags: list[str]
    created_at: str | None = None
    updated_at: str | None = None


class KBCreate(BaseModel):
    title: str = Field(min_length=1)
    content: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    org_id: str | None = None


class KBUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


class TicketResponse(BaseModel):
    id: str
    org_id: str | None = None
    conversation_id: str | None = None
    status: str
    priority: str
    subject: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: str | None = None


class OrgCreate(BaseModel):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)


class MemberResponse(BaseModel):
    id: str
    org_id: str
    user_id: str
    role: Literal["admin", "agent", "viewer"]
    created_at: str | None = None


class MemberCreate(BaseModel):
    org_id: str | None = None
    user_id: str = Field(min_length=1)
    role: Literal["admin", "agent", "viewer"]


class AgentRunResponse(BaseModel):
    id: str
    org_id: str | None = None
    conversation_id: str | None = None
    action: str
    confidence: float | None = None
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    citations: list[dict[str, Any]] | None = None
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None


class IngestRequest(BaseModel):
    document_id: str
    org_id: str | None = None
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
        usage = payload.get("usage", {})
        log_event(
            logging.INFO,
            "embedding_usage",
            model=self.model,
            input_count=len(texts),
            prompt_tokens=usage.get("prompt_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
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


def precheck_action(message: str) -> tuple[str, str, float] | None:
    msg = message.strip().lower()
    tags = extract_hash_tags(msg)
    if "#" in msg:
        log_event(
            logging.INFO,
            "precheck_hashtag_parsed",
            tags=tags,
            word_count=len(msg.split()),
        )
    if not msg:  # empty or whitespace
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

    if tags:
        return None

    if len(msg.split()) < 4:
        return (
            "Can you add more context (account, steps, and expected behavior)?",
            "ask_clarifying",
            0.45,
        )

    return None


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


def extract_keywords(message: str) -> list[str]:
    tokens = re.split(r"[^a-zA-Z0-9]+", message.lower())
    keywords = [token for token in tokens if len(token) > 3]
    return keywords[:5]


def retrieve_kb_candidates(
    supabase: Client, message: str, org_id: str | None, limit: int = 3
) -> list[dict[str, Any]]:
    query = message.strip().replace(",", " ")
    if not query:
        return []

    def kb_query():
        base = supabase.table("kb_documents").select("*")
        if org_id:
            base = base.eq("org_id", org_id)
        return base

    tags = extract_hash_tags(query)
    try:
        if tags:
            tag_value = tags[0]
            tagged = (
                kb_query().contains("tags", [tag_value])
                .limit(limit)
                .execute()
            )
            log_event(
                logging.INFO,
                "kb_tag_lookup",
                tag=tag_value,
                org_id=org_id,
                match_count=len(tagged.data or []),
            )
            if tagged.data:
                return tagged.data

        keywords = extract_keywords(query)
        if keywords:
            or_parts = []
            for keyword in keywords:
                or_parts.append(f"title.ilike.%{keyword}%")
                or_parts.append(f"content.ilike.%{keyword}%")
            text = (
                kb_query().or_(",".join(or_parts))
                .limit(limit)
                .execute()
            )
            return text.data or []

        text = (
            kb_query().or_(f"title.ilike.%{query}%,content.ilike.%{query}%")
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


def build_kb_chunk_reply(chunk: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    title = chunk.get("document_title") or "Knowledge Base"
    content = chunk.get("content", "")
    excerpt = content.strip().replace("\n", " ")
    if len(excerpt) > 360:
        excerpt = f"{excerpt[:360].rstrip()}..."
    reply = f"{title}: {excerpt}"
    citations = [
        {
            "kb_document_id": chunk.get("document_id", ""),
            "kb_chunk_id": chunk.get("id", ""),
        }
    ]
    return reply, citations


def retrieve_kb_vector_matches(
    supabase: Client,
    message: str,
    org_id: str | None,
    limit: int = 3,
    min_similarity: float = 0.2,
) -> tuple[list[dict[str, Any]], float | None]:
    enabled = os.getenv("VECTOR_SEARCH_ENABLED", "false").lower() == "true"
    if not enabled:
        return [], None

    try:
        provider = get_embedding_provider()
    except RuntimeError as exc:
        log_event(logging.WARNING, "embedding_not_configured", error=str(exc))
        return [], None

    try:
        embedding = provider.embed([message])[0]
        result = (
            supabase.rpc(
                "match_kb_chunks",
                {
                    "query_embedding": embedding,
                    "match_count": limit,
                    "min_similarity": min_similarity,
                    "p_org_id": org_id,
                },
            )
            .execute()
        )
        data = result.data or []
        top_similarity = data[0].get("similarity") if data else None
        log_event(
            logging.INFO,
            "kb_vector_matches",
            count=len(data),
            top_similarity=top_similarity,
            min_similarity=min_similarity,
        )
        return data, top_similarity
    except Exception as exc:
        log_event(logging.ERROR, "kb_vector_search_error", error=str(exc))
        return [], None


def retrieve_kb_reply(
    supabase: Client, message: str, org_id: str | None
) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
    limit = int(os.getenv("VECTOR_MATCH_COUNT", "3"))
    min_similarity = float(os.getenv("VECTOR_MIN_SIMILARITY", "0.2"))

    vector_matches, top_similarity = retrieve_kb_vector_matches(
        supabase,
        message,
        org_id,
        limit=limit,
        min_similarity=min_similarity,
    )
    if vector_matches:
        reply, citations = build_kb_chunk_reply(vector_matches[0])
        return (
            reply,
            citations,
            0.9,
            {"retrieval_source": "vector", "top_similarity": top_similarity},
        )

    doc_matches = retrieve_kb_candidates(supabase, message, org_id)
    if doc_matches:
        reply, citations = build_kb_reply(doc_matches[0])
        return reply, citations, 0.85, {"retrieval_source": "document"}

    return None


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


def get_ingest_config() -> tuple[int, int, bool]:
    chunk_size = int(os.getenv("INGEST_CHUNK_SIZE", "120"))
    chunk_overlap = int(os.getenv("INGEST_CHUNK_OVERLAP", "20"))
    auto_ingest = os.getenv("AUTO_INGEST_ON_KB_WRITE", "false").lower() == "true"
    return chunk_size, chunk_overlap, auto_ingest


def run_ingest(
    supabase: Client,
    provider: EmbeddingProvider,
    document_id: str,
    org_id: str | None,
    chunk_size: int,
    chunk_overlap: int,
    force: bool,
) -> IngestResponse:
    log_event(
        logging.INFO,
        "ingest_start",
        document_id=document_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        force=force,
    )

    try:
        query = supabase.table("kb_documents").select("*").eq("id", document_id)
        if org_id:
            query = query.eq("org_id", org_id)
        doc_result = query.limit(1).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc_result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    document = doc_result.data[0]
    doc_org_id = document.get("org_id")
    if not doc_org_id:
        log_event(logging.ERROR, "kb_missing_org", document_id=document_id)
        raise HTTPException(status_code=500, detail="kb_missing_org")
    chunks = chunk_text(document.get("content", ""), chunk_size, chunk_overlap)
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
            .eq("document_id", document_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    existing_hashes = {
        row.get("chunk_hash"): row.get("id")
        for row in (existing.data or [])
        if row.get("chunk_hash")
    }
    new_hashes = set(unique_map.keys())

    chunks_deleted = 0
    if not force:
        to_delete = [
            row_id for chash, row_id in existing_hashes.items() if chash not in new_hashes
        ]
    else:
        to_delete = [row_id for row_id in existing_hashes.values()]

    if to_delete:
        try:
            supabase.table("kb_chunks").delete().in_("id", to_delete).execute()
            chunks_deleted = len(to_delete)
        except Exception as exc:
            log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    if force:
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
                    "document_id": document_id,
                    "org_id": doc_org_id,
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
            log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    chunks_total = len(unique_chunks)
    chunks_skipped = chunks_total - chunks_inserted

    log_event(
        logging.INFO,
        "ingest_complete",
        document_id=document_id,
        chunks_total=chunks_total,
        chunks_inserted=chunks_inserted,
        chunks_skipped=chunks_skipped,
        chunks_deleted=chunks_deleted,
    )

    return IngestResponse(
        document_id=document_id,
        chunks_total=chunks_total,
        chunks_inserted=chunks_inserted,
        chunks_skipped=chunks_skipped,
        chunks_deleted=chunks_deleted,
        embedding_model=provider.model,
        embedding_version=provider.version,
    )


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
    start_time = perf_counter()
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, auth_user_id = resolve_org_context(supabase, request, payload.org_id)
    user_id = auth_user_id or payload.user_id
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    client_host = request.client.host if request.client else "unknown"

    log_event(
        logging.INFO,
        "chat_request",
        conversation_id=conversation_id,
        user_id=user_id,
        org_id=org_id,
        channel=payload.channel,
        client_ip=client_host,
    )

    try:
        if payload.conversation_id is None:
            supabase.table("conversations").insert(
                {
                    "id": conversation_id,
                    "org_id": org_id,
                    "user_id": user_id,
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

        kb_reply = None
        citations = None
        run_metadata: dict[str, Any] = {"retrieval_source": "none"}

        precheck = precheck_action(payload.message)
        if precheck:
            reply, action, confidence = precheck
            run_metadata["precheck_action"] = action
        else:
            kb_reply = retrieve_kb_reply(supabase, payload.message, org_id)
            if kb_reply:
                reply, citations, confidence, run_metadata = kb_reply
                action = "reply"
            else:
                reply, action, confidence = decide_response(payload.message)
        ticket_id = None
        if action in ("create_ticket", "escalate"):
            ticket_result = supabase.table("tickets").insert(
                {
                    "org_id": org_id,
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

        latency_ms = int((perf_counter() - start_time) * 1000)
        run_input = {
            "message": payload.message,
            "channel": payload.channel,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "org_id": org_id,
        }
        run_output = {
            "reply": reply,
            "action": action,
            "confidence": confidence,
            "ticket_id": ticket_id,
            "citations": citations,
        }
        try:
            supabase.table("agent_runs").insert(
                {
                    "org_id": org_id,
                    "conversation_id": conversation_id,
                    "action": action,
                    "confidence": confidence,
                    "input": run_input,
                    "output": run_output,
                    "citations": citations,
                    "latency_ms": latency_ms,
                    "metadata": run_metadata,
                }
            ).execute()
        except Exception as exc:
            log_event(
                logging.WARNING,
                "agent_run_insert_failed",
                conversation_id=conversation_id,
                error=str(exc),
            )
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


@app.get("/v1/orgs", response_model=list[OrgResponse])
async def list_orgs(request: Request) -> list[OrgResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    try:
        if auth_enabled():
            user_id = get_auth_user(request)
            memberships = load_memberships(supabase, user_id)
            org_ids = [
                member.get("org_id") for member in memberships if member.get("org_id")
            ]
            if not org_ids:
                return []
            result = (
                supabase.table("orgs")
                .select("*")
                .in_("id", org_ids)
                .order("created_at", desc=True)
                .execute()
            )
        else:
            result = (
                supabase.table("orgs")
                .select("*")
                .order("created_at", desc=True)
                .execute()
            )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [OrgResponse(**org) for org in (result.data or [])]


@app.post("/v1/orgs", response_model=OrgResponse, status_code=201)
async def create_org(payload: OrgCreate, request: Request) -> OrgResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    user_id = get_auth_user(request)
    data = payload.model_dump()
    data["slug"] = data["slug"].strip().lower()
    try:
        result = supabase.table("orgs").insert(data).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=500, detail="org_create_failed")

    org = result.data[0]
    if auth_enabled() and user_id:
        try:
            supabase.table("members").insert(
                {"org_id": org["id"], "user_id": user_id, "role": "admin"}
            ).execute()
        except Exception as exc:
            log_event(logging.ERROR, "db_error", error=str(exc))
            raise HTTPException(status_code=500, detail="member_create_failed")
    return OrgResponse(**org)


@app.get("/v1/orgs/{org_id}", response_model=OrgResponse)
async def get_org(org_id: str, request: Request) -> OrgResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    user_id = get_auth_user(request)
    if auth_enabled():
        resolve_org_id(supabase, request, org_id, user_id)
    try:
        result = supabase.table("orgs").select("*").eq("id", org_id).limit(1).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", org_id=org_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="org_not_found")

    return OrgResponse(**result.data[0])


@app.get("/v1/members", response_model=list[MemberResponse])
async def list_members(request: Request, org_id: str | None = None) -> list[MemberResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    resolved_org_id, _ = resolve_org_context(supabase, request, org_id)
    try:
        result = (
            supabase.table("members")
            .select("*")
            .eq("org_id", resolved_org_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [MemberResponse(**member) for member in (result.data or [])]


@app.post("/v1/members", response_model=MemberResponse, status_code=201)
async def create_member(payload: MemberCreate, request: Request) -> MemberResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, user_id = resolve_org_context(supabase, request, payload.org_id)
    ensure_admin_access(supabase, org_id, user_id)
    data = payload.model_dump()
    data["org_id"] = org_id
    try:
        result = supabase.table("members").insert(data).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=500, detail="member_create_failed")

    return MemberResponse(**result.data[0])


@app.get("/v1/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, request: Request) -> TicketResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    try:
        result = (
            supabase.table("tickets")
            .select("*")
            .eq("id", ticket_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", ticket_id=ticket_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="ticket_not_found")

    ticket = result.data[0]
    return TicketResponse(**ticket)


@app.get("/v1/tickets", response_model=list[TicketResponse])
async def list_tickets(request: Request, limit: int = 50) -> list[TicketResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    safe_limit = max(1, min(limit, 100))
    try:
        result = (
            supabase.table("tickets")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [TicketResponse(**ticket) for ticket in (result.data or [])]


@app.get("/v1/runs", response_model=list[AgentRunResponse])
async def list_runs(
    request: Request,
    limit: int = 50,
    conversation_id: str | None = None,
) -> list[AgentRunResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    safe_limit = max(1, min(limit, 100))
    try:
        query = (
            supabase.table("agent_runs")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(safe_limit)
        )
        if conversation_id:
            query = query.eq("conversation_id", conversation_id)
        result = query.execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [AgentRunResponse(**run) for run in (result.data or [])]


@app.get("/v1/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(run_id: str, request: Request) -> AgentRunResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    try:
        result = (
            supabase.table("agent_runs")
            .select("*")
            .eq("id", run_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", run_id=run_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="run_not_found")

    return AgentRunResponse(**result.data[0])


@app.get("/v1/kb", response_model=list[KBDocument])
async def list_kb(request: Request) -> list[KBDocument]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    try:
        result = (
            supabase.table("kb_documents")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [KBDocument(**doc) for doc in (result.data or [])]


@app.post("/v1/kb", response_model=KBDocument, status_code=201)
async def create_kb(payload: KBCreate, request: Request) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, user_id = resolve_org_context(supabase, request, payload.org_id)
    ensure_write_access(request, supabase, org_id, user_id)
    data = payload.model_dump()
    data["tags"] = normalize_tags(data.get("tags") or [])
    data["org_id"] = org_id

    try:
        result = supabase.table("kb_documents").insert(data).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=500, detail="kb_create_failed")

    doc = result.data[0]
    _, _, auto_ingest = get_ingest_config()
    if auto_ingest:
        try:
            provider = get_embedding_provider()
            chunk_size, chunk_overlap, _ = get_ingest_config()
            run_ingest(
                supabase,
                provider,
                doc["id"],
                doc.get("org_id"),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                force=False,
            )
        except Exception as exc:
            log_event(
                logging.WARNING,
                "auto_ingest_failed",
                document_id=doc.get("id"),
                error=str(exc),
            )
    else:
        log_event(logging.INFO, "auto_ingest_skipped", document_id=doc.get("id"))

    return KBDocument(**doc)


@app.get("/v1/kb/{doc_id}", response_model=KBDocument)
async def get_kb(doc_id: str, request: Request) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, _ = resolve_org_context(supabase, request)
    try:
        result = (
            supabase.table("kb_documents")
            .select("*")
            .eq("id", doc_id)
            .eq("org_id", org_id)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    return KBDocument(**result.data[0])


@app.patch("/v1/kb/{doc_id}", response_model=KBDocument)
async def update_kb(doc_id: str, payload: KBUpdate, request: Request) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    org_id, user_id = resolve_org_context(supabase, request)
    ensure_write_access(request, supabase, org_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if "tags" in updates and updates["tags"] is not None:
        updates["tags"] = normalize_tags(updates["tags"])
    updates["updated_at"] = utc_now()

    try:
        result = (
            supabase.table("kb_documents")
            .update(updates)
            .eq("id", doc_id)
            .eq("org_id", org_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    doc = result.data[0]
    _, _, auto_ingest = get_ingest_config()
    if auto_ingest:
        try:
            provider = get_embedding_provider()
            chunk_size, chunk_overlap, _ = get_ingest_config()
            run_ingest(
                supabase,
                provider,
                doc["id"],
                doc.get("org_id"),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                force=False,
            )
        except Exception as exc:
            log_event(
                logging.WARNING,
                "auto_ingest_failed",
                document_id=doc.get("id"),
                error=str(exc),
            )
    else:
        log_event(logging.INFO, "auto_ingest_skipped", document_id=doc.get("id"))

    return KBDocument(**doc)


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest, request: Request) -> IngestResponse:
    try:
        supabase = get_supabase_client()
        provider = get_embedding_provider()
    except RuntimeError as exc:
        log_event(logging.ERROR, "ingest_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="ingest_not_configured")
    org_id, _ = resolve_org_context(supabase, request, payload.org_id)
    return run_ingest(
        supabase,
        provider,
        payload.document_id,
        org_id,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        force=payload.force,
    )
