import logging
from typing import Any

from .logging_utils import log_event
from .ports import MessagesRepo


def load_recent_messages(
    messages_repo: MessagesRepo, conversation_id: str, limit: int
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    try:
        result = messages_repo.list_messages(conversation_id, limit)
    except Exception as exc:
        log_event(
            logging.WARNING,
            "context_load_failed",
            conversation_id=conversation_id,
            error=str(exc),
        )
        return []
    return list(reversed(result))


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
