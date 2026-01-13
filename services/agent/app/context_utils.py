import logging
from typing import Any

from supabase import Client

from .logging_utils import log_event


def load_recent_messages(
    supabase: Client, conversation_id: str, limit: int
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    try:
        result = (
            supabase.table("messages")
            .select("role,content,created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as exc:
        log_event(
            logging.WARNING,
            "context_load_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
        return []
    data = result.data or []
    return list(reversed(data))


def build_context(messages: list[dict[str, Any]], max_chars: int) -> str:
    if not messages:
        return ""
    lines: list[str] = []
    for message in messages:
        role = message.get("role")
        if role not in ("user", "assistant", "system"):
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        normalized = " ".join(content.split())
        lines.append(f"{role}: {normalized}")
    context = "\n".join(lines).strip()
    if max_chars > 0 and len(context) > max_chars:
        context = context[-max_chars:]
    return context
