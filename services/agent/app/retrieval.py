import logging
import re
from typing import Any

from .logging_utils import log_event


def decide_response(message: str) -> tuple[str, str, float, str]:
    msg = message.strip().lower()
    if not msg:
        return (
            "Please share a bit more detail so I can help.",
            "ask_clarifying",
            0.2,
            "heuristic_empty",
        )

    ticket_keywords = ("bug", "error", "issue", "incident", "crash", "outage", "fail")
    if any(keyword in msg for keyword in ticket_keywords):
        return (
            "Thanks for reporting this. I am creating a ticket and will follow up with next steps.",
            "create_ticket",
            0.35,
            "heuristic_ticket_keyword",
        )

    if any(keyword in msg for keyword in ("integration", "integrations", "webhook", "api")):
        return (
            "Can you share the provider/tool, endpoint or event, and any error you see?",
            "ask_clarifying",
            0.45,
            "heuristic_integration",
        )

    if len(msg.split()) < 4:
        return (
            "Can you add more context (account, steps, and expected behavior)?",
            "ask_clarifying",
            0.45,
            "heuristic_short",
        )

    return (
        "Thanks. I am checking our knowledge base. For now, try restarting the app and share any error code.",
        "reply",
        0.7,
        "heuristic_generic_reply",
    )


def precheck_action(message: str) -> tuple[str, str, float, str] | None:
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
            "precheck_empty",
        )

    ticket_keywords = ("bug", "error", "issue", "incident", "crash", "outage", "fail")
    if any(keyword in msg for keyword in ticket_keywords):
        return (
            "Thanks for reporting this. I am creating a ticket and will follow up with next steps.",
            "create_ticket",
            0.35,
            "precheck_ticket_keyword",
        )

    if tags:
        return None

    if len(msg.split()) < 4:
        return (
            "Can you add more context (account, steps, and expected behavior)?",
            "ask_clarifying",
            0.45,
            "precheck_short",
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

