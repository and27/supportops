from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .auth_utils import auth_enabled, get_auth_user
from .context_utils import build_context, load_recent_messages
from .embeddings import get_embedding_provider
from .ingest import get_ingest_config, run_ingest
from .logging_utils import log_event
from .prompts import get_clarify_prompt
from .adapters.retriever_adapter import get_retriever
from .adapters.supabase_repos import (
    SupabaseConversationsRepo,
    SupabaseKBChunksRepo,
    SupabaseKBRepo,
    SupabaseMembersRepo,
    SupabaseMessagesRepo,
    SupabaseOrgsRepo,
    SupabaseRunsRepo,
    SupabaseTicketsRepo,
)
from .orgs import (
    ensure_admin_access,
    ensure_write_access,
    load_memberships,
    resolve_org_context,
    resolve_org_id,
)
from .retrieval import decide_response, normalize_tags, precheck_action
from .schemas import (
    AgentRunResponse,
    ChatRequest,
    ChatResponse,
    ConversationResponse,
    IngestRequest,
    IngestResponse,
    KBCreate,
    KBDocument,
    KBUpdate,
    MessageResponse,
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


def extract_eval_metadata(
    metadata: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    if not metadata:
        return None, None
    eval_payload = metadata.get("eval")
    if isinstance(eval_payload, dict):
        expected = eval_payload.get("expected_action") or eval_payload.get("action")
        category = eval_payload.get("category")
        return expected, category
    expected = metadata.get("expected_action") or metadata.get("eval_expected_action")
    category = metadata.get("category") or metadata.get("eval_category")
    return expected, category

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

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, auth_user_id = resolve_org_context(
        orgs_repo, members_repo, request, payload.org_id
    )
    user_id = auth_user_id or payload.user_id
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    input_length_chars = len(payload.message or "")
    kb_repo = SupabaseKBRepo(supabase)
    retriever = get_retriever(supabase, kb_repo)
    conversations_repo = SupabaseConversationsRepo(supabase)
    messages_repo = SupabaseMessagesRepo(supabase)
    tickets_repo = SupabaseTicketsRepo(supabase)
    runs_repo = SupabaseRunsRepo(supabase)

    log_event(
        logging.INFO,
        "chat_request",
        conversation_id=conversation_id,
        user_id=user_id,
        org_id=org_id,
        channel=payload.channel,
    )
    log_event(
        logging.INFO,
        "request_started",
        conversation_id=conversation_id,
        tenant_id=org_id,
        channel=payload.channel,
        input_length_chars=input_length_chars,
    )

    try:
        if payload.conversation_id is None:
            conversations_repo.create_conversation(
                {
                    "id": conversation_id,
                    "org_id": org_id,
                    "user_id": user_id,
                    "channel": payload.channel,
                    "metadata": payload.metadata,
                }
            )

        context_message_limit = int(os.getenv("CONTEXT_MESSAGE_LIMIT", "6"))
        context_max_chars = int(os.getenv("CONTEXT_MAX_CHARS", "1200"))
        prior_messages = []
        context_text = ""
        if payload.conversation_id:
            prior_messages = load_recent_messages(
                messages_repo, conversation_id, context_message_limit
            )
            context_text = build_context(prior_messages, context_max_chars)

        messages_repo.create_message(
            {
                "conversation_id": conversation_id,
                "role": "user",
                "content": payload.message,
            }
        )

        kb_reply = None
        citations = None
        run_metadata: dict[str, Any] = {"retrieval_source": "none"}
        guardrail_reason = None
        decision_reason: str | None = None
        decision_message = payload.message
        retrieval_query = payload.message
        retrieval_ms = 0
        clarify_prompt = get_clarify_prompt()
        if context_text:
            decision_message = f"{context_text}\nuser: {payload.message}"
            run_metadata["context_messages"] = len(prior_messages)
            run_metadata["context_chars"] = len(context_text)
            run_metadata["context_used"] = True
            user_context = [
                message.get("content", "").strip()
                for message in prior_messages
                if message.get("role") == "user" and message.get("content")
            ]
            last_assistant = next(
                (
                    message.get("content", "").strip()
                    for message in reversed(prior_messages)
                    if message.get("role") == "assistant"
                ),
                "",
            )
            if last_assistant == clarify_prompt and user_context:
                recent_users = user_context[-2:]
                retrieval_query = "\n".join(recent_users + [payload.message]).strip()
        else:
            run_metadata["context_used"] = False

        precheck = precheck_action(decision_message)
        if precheck:
            reply, action, confidence, decision_reason = precheck
            run_metadata["precheck_action"] = action
            run_metadata["decision_source"] = "precheck"
        else:
            retrieval_start = perf_counter()
            kb_reply = retriever.retrieve(retrieval_query, org_id, conversation_id)
            retrieval_ms = int((perf_counter() - retrieval_start) * 1000)
            if kb_reply:
                reply, citations, confidence, run_metadata = kb_reply
                action = "reply"
                run_metadata["decision_source"] = "kb"
                decision_reason = (
                    "kb_vector_match"
                    if run_metadata.get("retrieval_source") == "vector"
                    else "kb_document_match"
                )
            else:
                reply, action, confidence, decision_reason = decide_response(
                    decision_message
                )
                run_metadata["decision_source"] = "heuristic"
        retrieval_source = run_metadata.get("retrieval_source") or "none"
        if retrieval_source == "vector":
            retrieval_candidates_count = int(run_metadata.get("match_count") or 0)
        elif retrieval_source == "document":
            retrieval_candidates_count = int(run_metadata.get("document_match_count") or 0)
        else:
            retrieval_candidates_count = 0
        top_similarity = run_metadata.get("top_similarity")
        log_event(
            logging.INFO,
            "retrieval_done",
            conversation_id=conversation_id,
            tenant_id=org_id,
            channel=payload.channel,
            retrieval_ms=retrieval_ms,
            retrieval_candidates_count=retrieval_candidates_count,
            top_similarity=top_similarity,
            retrieval_source=retrieval_source,
        )
        reply_min_similarity = float(os.getenv("REPLY_MIN_SIMILARITY", "0.35"))
        if action == "reply" and run_metadata.get("retrieval_source") == "vector":
            clarify_prompt = get_clarify_prompt()
            run_metadata["reply_min_similarity"] = reply_min_similarity
            top_similarity = run_metadata.get("top_similarity")
            if isinstance(top_similarity, (int, float)) and top_similarity < reply_min_similarity:
                guardrail_reason = "low_similarity"
                run_metadata["guardrail"] = guardrail_reason
                run_metadata["guardrail_original_action"] = action
                run_metadata["decision_reason_original"] = decision_reason
                action = "ask_clarifying"
                confidence = min(confidence, 0.4)
                reply = clarify_prompt
                citations = None
                run_metadata["decision_source"] = "guardrail"
                decision_reason = "guardrail_low_similarity"
        if action == "reply" and not citations:
            clarify_prompt = get_clarify_prompt()
            guardrail_reason = "missing_citations"
            run_metadata["guardrail"] = guardrail_reason
            run_metadata["guardrail_original_action"] = action
            run_metadata["decision_reason_original"] = decision_reason
            action = "ask_clarifying"
            confidence = min(confidence, 0.4)
            reply = clarify_prompt
            citations = None
            run_metadata["decision_source"] = "guardrail"
            decision_reason = "guardrail_missing_citations"
        if decision_reason:
            run_metadata["decision_reason"] = decision_reason
        if not decision_reason:
            decision_reason = "unspecified"
            run_metadata["decision_reason"] = decision_reason
        decision = action
        handoff_type = None
        if action in ("create_ticket", "escalate"):
            decision = "handoff"
            handoff_type = action
        guardrails_triggered = [guardrail_reason] if guardrail_reason else []
        log_event(
            logging.INFO,
            "decision_made",
            conversation_id=conversation_id,
            tenant_id=org_id,
            channel=payload.channel,
            decision=decision,
            decision_reason=decision_reason,
            guardrails_triggered=guardrails_triggered,
            has_citations=bool(citations),
            handoff_type=handoff_type,
        )

        expected_action, eval_category = extract_eval_metadata(payload.metadata)
        if expected_action:
            run_metadata["eval_expected_action"] = expected_action
            run_metadata["eval_category"] = eval_category or "uncategorized"
            run_metadata["eval_action_match"] = action == expected_action
            log_event(
                logging.INFO,
                "eval_action_result",
                conversation_id=conversation_id,
                expected_action=expected_action,
                actual_action=action,
                category=eval_category or "uncategorized",
                match=action == expected_action,
            )
        ticket_id = None
        if action in ("create_ticket", "escalate"):
            ticket_result = tickets_repo.create_ticket(
                {
                    "org_id": org_id,
                    "conversation_id": conversation_id,
                    "subject": payload.message[:160],
                }
            )
            if ticket_result:
                ticket_id = ticket_result.get("id")
            if not ticket_id:
                raise RuntimeError("ticket_insert_failed")

        messages_repo.create_message(
            {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": reply,
                "metadata": {"citations": citations} if citations else None,
            }
        )

        latency_ms = int((perf_counter() - start_time) * 1000)
        response_tokens_estimated = int(len(reply or "") / 4)
        response_event = "handoff_sent" if decision == "handoff" else "reply_sent"
        log_event(
            logging.INFO,
            response_event,
            conversation_id=conversation_id,
            tenant_id=org_id,
            channel=payload.channel,
            response_tokens_estimated=response_tokens_estimated,
            latency_ms_total=latency_ms,
            handoff_type=handoff_type,
        )
        run_input = {
            "message": payload.message,
            "decision_message": decision_message,
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
            "decision_reason": decision_reason,
            "decision_source": run_metadata.get("decision_source"),
            "guardrail": guardrail_reason,
        }
        try:
            runs_repo.create_run(
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
            )
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
        decision_reason=decision_reason,
    )

    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        action=action,
        confidence=confidence,
        ticket_id=ticket_id,
        citations=citations,
        decision_reason=decision_reason,
        decision_source=run_metadata.get("decision_source"),
        guardrail=guardrail_reason,
    )


@app.get("/v1/orgs", response_model=list[OrgResponse])
async def list_orgs(request: Request) -> list[OrgResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_ids: list[str] | None = None
    if auth_enabled():
        user_id = get_auth_user(request)
        memberships = load_memberships(members_repo, user_id)
        org_ids = [member.get("org_id") for member in memberships if member.get("org_id")]
        if not org_ids:
            return []
        orgs = []
        for org_id in org_ids[:100]:
            org = orgs_repo.get_org(org_id)
            if org:
                orgs.append(org)
        return [OrgResponse(**org) for org in orgs]

    try:
        orgs = orgs_repo.list_orgs(100)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [OrgResponse(**org) for org in orgs]


@app.post("/v1/orgs", response_model=OrgResponse, status_code=201)
async def create_org(payload: OrgCreate, request: Request) -> OrgResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    user_id = get_auth_user(request)
    data = payload.model_dump()
    data["slug"] = data["slug"].strip().lower()
    try:
        org = orgs_repo.create_org(data)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not org:
        raise HTTPException(status_code=500, detail="org_create_failed")

    if auth_enabled() and user_id:
        try:
            members_repo.create_member(
                {"org_id": org["id"], "user_id": user_id, "role": "admin"}
            )
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

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    user_id = get_auth_user(request)
    if auth_enabled():
        resolve_org_id(orgs_repo, members_repo, request, org_id, user_id)
    try:
        org = orgs_repo.get_org(org_id)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", org_id=org_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not org:
        raise HTTPException(status_code=404, detail="org_not_found")

    return OrgResponse(**org)


@app.get("/v1/members", response_model=list[MemberResponse])
async def list_members(request: Request, org_id: str | None = None) -> list[MemberResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    resolved_org_id, _ = resolve_org_context(
        orgs_repo, members_repo, request, org_id
    )
    try:
        members = members_repo.list_members(resolved_org_id, 200)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [MemberResponse(**member) for member in members]


@app.post("/v1/members", response_model=MemberResponse, status_code=201)
async def create_member(payload: MemberCreate, request: Request) -> MemberResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, user_id = resolve_org_context(
        orgs_repo, members_repo, request, payload.org_id
    )
    ensure_admin_access(members_repo, org_id, user_id)
    data = payload.model_dump()
    data["org_id"] = org_id
    try:
        member = members_repo.create_member(data)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not member:
        raise HTTPException(status_code=500, detail="member_create_failed")

    return MemberResponse(**member)


@app.get("/v1/tickets/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str, request: Request) -> TicketResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    tickets_repo = SupabaseTicketsRepo(supabase)
    try:
        ticket = tickets_repo.get_ticket(ticket_id)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", ticket_id=ticket_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not ticket or ticket.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="ticket_not_found")

    return TicketResponse(**ticket)


@app.get("/v1/tickets", response_model=list[TicketResponse])
async def list_tickets(request: Request, limit: int = 50) -> list[TicketResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    safe_limit = max(1, min(limit, 100))
    tickets_repo = SupabaseTicketsRepo(supabase)
    try:
        tickets = tickets_repo.list_tickets(org_id, safe_limit)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [TicketResponse(**ticket) for ticket in tickets]


@app.get("/v1/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    request: Request, limit: int = 20
) -> list[ConversationResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    safe_limit = max(1, min(limit, 100))
    conversations_repo = SupabaseConversationsRepo(supabase)
    try:
        conversations = conversations_repo.list_conversations(org_id, safe_limit)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [ConversationResponse(**row) for row in conversations]


@app.get(
    "/v1/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
)
async def list_conversation_messages(
    conversation_id: str,
    request: Request,
    limit: int = 50,
) -> list[MessageResponse]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    conversations_repo = SupabaseConversationsRepo(supabase)
    messages_repo = SupabaseMessagesRepo(supabase)
    try:
        convo = conversations_repo.get_conversation(conversation_id)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not convo or convo.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="conversation_not_found")

    safe_limit = max(1, min(limit, 200))
    try:
        messages = messages_repo.list_messages(conversation_id, safe_limit)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [MessageResponse(**row) for row in messages]


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

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    safe_limit = max(1, min(limit, 100))
    runs_repo = SupabaseRunsRepo(supabase)
    try:
        if conversation_id:
            runs = runs_repo.list_runs_for_conversation(
                org_id, conversation_id, safe_limit
            )
        else:
            runs = runs_repo.list_runs(org_id, safe_limit)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [AgentRunResponse(**run) for run in runs]


@app.get("/v1/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(run_id: str, request: Request) -> AgentRunResponse:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    runs_repo = SupabaseRunsRepo(supabase)
    try:
        run = runs_repo.get_run(run_id)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", run_id=run_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not run or run.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="run_not_found")

    return AgentRunResponse(**run)


@app.get("/v1/kb", response_model=list[KBDocument])
async def list_kb(request: Request) -> list[KBDocument]:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    kb_repo = SupabaseKBRepo(supabase)
    try:
        documents = kb_repo.list_documents(org_id, 200)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    return [KBDocument(**doc) for doc in documents]


@app.post("/v1/kb", response_model=KBDocument, status_code=201)
async def create_kb(payload: KBCreate, request: Request) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, user_id = resolve_org_context(
        orgs_repo, members_repo, request, payload.org_id
    )
    ensure_write_access(request, members_repo, org_id, user_id)
    data = payload.model_dump()
    data["tags"] = normalize_tags(data.get("tags") or [])
    data["org_id"] = org_id
    kb_repo = SupabaseKBRepo(supabase)

    try:
        doc = kb_repo.create_document(data)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc:
        raise HTTPException(status_code=500, detail="kb_create_failed")

    _, _, auto_ingest = get_ingest_config()
    if auto_ingest:
        try:
            provider = get_embedding_provider()
            chunk_size, chunk_overlap, _ = get_ingest_config()
            run_ingest(
                kb_repo,
                SupabaseKBChunksRepo(supabase),
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

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request)
    kb_repo = SupabaseKBRepo(supabase)
    try:
        doc = kb_repo.get_document(doc_id)
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc or doc.get("org_id") != org_id:
        raise HTTPException(status_code=404, detail="kb_not_found")

    return KBDocument(**doc)


@app.patch("/v1/kb/{doc_id}", response_model=KBDocument)
async def update_kb(doc_id: str, payload: KBUpdate, request: Request) -> KBDocument:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, user_id = resolve_org_context(orgs_repo, members_repo, request)
    ensure_write_access(request, members_repo, org_id, user_id)
    updates = payload.model_dump(exclude_unset=True)
    if "tags" in updates and updates["tags"] is not None:
        updates["tags"] = normalize_tags(updates["tags"])
    updates["updated_at"] = utc_now()
    kb_repo = SupabaseKBRepo(supabase)

    try:
        existing = kb_repo.get_document(doc_id)
        if not existing or existing.get("org_id") != org_id:
            raise HTTPException(status_code=404, detail="kb_not_found")
        doc = kb_repo.update_document(doc_id, updates)
    except HTTPException:
        raise
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc:
        raise HTTPException(status_code=404, detail="kb_not_found")

    _, _, auto_ingest = get_ingest_config()
    if auto_ingest:
        try:
            provider = get_embedding_provider()
            chunk_size, chunk_overlap, _ = get_ingest_config()
            run_ingest(
                kb_repo,
                SupabaseKBChunksRepo(supabase),
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


@app.delete("/v1/kb/{doc_id}", status_code=204)
async def delete_kb(doc_id: str, request: Request) -> Response:
    try:
        supabase = get_supabase_client()
    except RuntimeError as exc:
        log_event(logging.ERROR, "supabase_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="supabase_not_configured")

    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, user_id = resolve_org_context(orgs_repo, members_repo, request)
    ensure_write_access(request, members_repo, org_id, user_id)
    kb_repo = SupabaseKBRepo(supabase)

    try:
        existing = kb_repo.get_document(doc_id)
        if not existing or existing.get("org_id") != org_id:
            raise HTTPException(status_code=404, detail="kb_not_found")
        deleted = kb_repo.delete_document(doc_id)
    except HTTPException:
        raise
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=doc_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not deleted:
        raise HTTPException(status_code=500, detail="kb_delete_failed")

    return Response(status_code=204)


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(payload: IngestRequest, request: Request) -> IngestResponse:
    try:
        supabase = get_supabase_client()
        provider = get_embedding_provider()
    except RuntimeError as exc:
        log_event(logging.ERROR, "ingest_not_configured", error=str(exc))
        raise HTTPException(status_code=500, detail="ingest_not_configured")
    orgs_repo = SupabaseOrgsRepo(supabase)
    members_repo = SupabaseMembersRepo(supabase)
    org_id, _ = resolve_org_context(orgs_repo, members_repo, request, payload.org_id)
    kb_repo = SupabaseKBRepo(supabase)
    chunks_repo = SupabaseKBChunksRepo(supabase)
    return run_ingest(
        kb_repo,
        chunks_repo,
        provider,
        payload.document_id,
        org_id,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap,
        force=payload.force,
    )
