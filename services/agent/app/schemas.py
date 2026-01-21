from typing import Any, Literal

from pydantic import BaseModel, Field


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
    citations: list[dict[str, Any]] | None = None
    decision_reason: str | None = None
    decision_source: str | None = None
    guardrail: str | None = None


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


class ConversationResponse(BaseModel):
    id: str
    org_id: str | None = None
    user_id: str | None = None
    channel: str
    created_at: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    metadata: dict[str, Any] | None = None
    created_at: str | None = None


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
