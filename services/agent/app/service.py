from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from .context_utils import build_context, load_recent_messages
from .logging_utils import log_event
from .prompts import get_clarify_prompt
from .retrieval import decide_response, precheck_action
from .schemas import ChatRequest, ChatResponse
from .ports import (
    ConversationsRepo,
    MessagesRepo,
    TicketsRepo,
    RunsRepo,
    Retriever,
)


@dataclass(frozen=True)
class PolicyConfig:
    context_message_limit: int
    context_max_chars: int
    reply_min_similarity: float


def get_policy_config() -> PolicyConfig:
    return PolicyConfig(
        context_message_limit=int(os.getenv("CONTEXT_MESSAGE_LIMIT", "6")),
        context_max_chars=int(os.getenv("CONTEXT_MAX_CHARS", "1200")),
        reply_min_similarity=float(os.getenv("REPLY_MIN_SIMILARITY", "0.35")),
    )


@dataclass(frozen=True)
class ChatDependencies:
    conversations_repo: ConversationsRepo
    messages_repo: MessagesRepo
    tickets_repo: TicketsRepo
    runs_repo: RunsRepo
    retriever: Retriever


class ServiceError(RuntimeError):
    def __init__(self, detail: str, conversation_id: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.conversation_id = conversation_id


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


def build_retrieval_query(
    payload: ChatRequest,
    context_text: str,
    prior_messages: list[dict[str, Any]],
) -> tuple[str, str, dict[str, Any]]:
    decision_message = payload.message
    retrieval_query = payload.message
    run_metadata: dict[str, Any] = {"context_used": False}
    if not context_text:
        return decision_message, retrieval_query, run_metadata

    run_metadata["context_used"] = True
    run_metadata["context_messages"] = len(prior_messages)
    run_metadata["context_chars"] = len(context_text)
    decision_message = f"{context_text}\nuser: {payload.message}"

    clarify_prompt = get_clarify_prompt()
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
    return decision_message, retrieval_query, run_metadata


def handle_chat(
    payload: ChatRequest,
    org_id: str,
    user_id: str | None,
    deps: ChatDependencies,
) -> ChatResponse:
    start_time = perf_counter()
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    input_length_chars = len(payload.message or "")
    policy = get_policy_config()

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
            deps.conversations_repo.create_conversation(
                {
                    "id": conversation_id,
                    "org_id": org_id,
                    "user_id": user_id,
                    "channel": payload.channel,
                    "metadata": payload.metadata,
                }
            )

        prior_messages = []
        context_text = ""
        if payload.conversation_id:
            prior_messages = load_recent_messages(
                deps.messages_repo, conversation_id, policy.context_message_limit
            )
            context_text = build_context(prior_messages, policy.context_max_chars)

        deps.messages_repo.create_message(
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

        decision_message, retrieval_query, context_metadata = build_retrieval_query(
            payload, context_text, prior_messages
        )
        run_metadata.update(context_metadata)

        precheck = precheck_action(decision_message)
        retrieval_ms = 0
        if precheck:
            reply, action, confidence, decision_reason = precheck
            run_metadata["precheck_action"] = action
            run_metadata["decision_source"] = "precheck"
        else:
            retrieval_start = perf_counter()
            kb_reply = deps.retriever.retrieve(
                retrieval_query, org_id, conversation_id
            )
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
            retrieval_candidates_count = int(
                run_metadata.get("document_match_count") or 0
            )
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

        if action == "reply" and run_metadata.get("retrieval_source") == "vector":
            run_metadata["reply_min_similarity"] = policy.reply_min_similarity
            top_similarity = run_metadata.get("top_similarity")
            if isinstance(top_similarity, (int, float)) and top_similarity < policy.reply_min_similarity:
                guardrail_reason = "low_similarity"
                run_metadata["guardrail"] = guardrail_reason
                run_metadata["guardrail_original_action"] = action
                run_metadata["decision_reason_original"] = decision_reason
                action = "ask_clarifying"
                confidence = min(confidence, 0.4)
                reply = get_clarify_prompt()
                citations = None
                run_metadata["decision_source"] = "guardrail"
                decision_reason = "guardrail_low_similarity"

        if action == "reply" and not citations:
            guardrail_reason = "missing_citations"
            run_metadata["guardrail"] = guardrail_reason
            run_metadata["guardrail_original_action"] = action
            run_metadata["decision_reason_original"] = decision_reason
            action = "ask_clarifying"
            confidence = min(confidence, 0.4)
            reply = get_clarify_prompt()
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
            ticket_result = deps.tickets_repo.create_ticket(
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

        deps.messages_repo.create_message(
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
            deps.runs_repo.create_run(
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
        raise ServiceError("db_error", conversation_id=conversation_id) from exc

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
