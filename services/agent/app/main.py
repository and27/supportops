from __future__ import annotations

import logging
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .auth_utils import auth_enabled, get_auth_user
from .embeddings import get_embedding_provider
from .ingest import get_ingest_config, run_ingest
from .logging_utils import log_event
from .orgs import (
    ensure_admin_access,
    ensure_write_access,
    load_memberships,
    resolve_org_context,
    resolve_org_id,
)
from .retrieval import decide_response, normalize_tags, precheck_action, retrieve_kb_reply
from .schemas import (
    AgentRunResponse,
    ChatRequest,
    ChatResponse,
    IngestRequest,
    IngestResponse,
    KBCreate,
    KBDocument,
    KBUpdate,
    MemberCreate,
    MemberResponse,
    OrgCreate,
    OrgResponse,
    TicketResponse,
)
from .supabase_client import get_supabase_client

agent_root = Path(__file__).resolve().parents[1]
load_dotenv(agent_root / ".env", override=False)
load_dotenv(agent_root / ".env.local", override=True)

app = FastAPI()

logging.basicConfig(level=logging.INFO, format="%(message)s")

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
        guardrail_reason = None

        precheck = precheck_action(payload.message)
        if precheck:
            reply, action, confidence = precheck
            run_metadata["precheck_action"] = action
            run_metadata["decision_source"] = "precheck"
        else:
            kb_reply = retrieve_kb_reply(supabase, payload.message, org_id)
            if kb_reply:
                reply, citations, confidence, run_metadata = kb_reply
                action = "reply"
                run_metadata["decision_source"] = "kb"
            else:
                reply, action, confidence = decide_response(payload.message)
                run_metadata["decision_source"] = "heuristic"
        reply_min_similarity = float(os.getenv("REPLY_MIN_SIMILARITY", "0.35"))
        if action == "reply" and run_metadata.get("retrieval_source") == "vector":
            run_metadata["reply_min_similarity"] = reply_min_similarity
            top_similarity = run_metadata.get("top_similarity")
            if isinstance(top_similarity, (int, float)) and top_similarity < reply_min_similarity:
                guardrail_reason = "low_similarity"
                run_metadata["guardrail"] = guardrail_reason
                run_metadata["guardrail_original_action"] = action
                action = "ask_clarifying"
                confidence = min(confidence, 0.4)
                reply = (
                    "Can you add more context (account, steps, and expected behavior)?"
                )
                citations = None
        if action == "reply" and not citations:
            guardrail_reason = "missing_citations"
            run_metadata["guardrail"] = guardrail_reason
            run_metadata["guardrail_original_action"] = action
            action = "ask_clarifying"
            confidence = min(confidence, 0.4)
            reply = (
                "Can you add more context (account, steps, and expected behavior)?"
            )
            citations = None
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
        latency_ms=latency_ms,
        retrieval_source=run_metadata.get("retrieval_source"),
        decision_source=run_metadata.get("decision_source"),
        guardrail=guardrail_reason,
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

    org_ids: list[str] | None = None
    if auth_enabled():
        user_id = get_auth_user(request)
        memberships = load_memberships(supabase, user_id)
        org_ids = [member.get("org_id") for member in memberships if member.get("org_id")]
        if not org_ids:
            return []

    try:
        query = supabase.table("orgs").select("*").order("created_at", desc=True)
        if org_ids:
            query = query.in_("id", org_ids)
        result = query.execute()
    except HTTPException:
        raise
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

