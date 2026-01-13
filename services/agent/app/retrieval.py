import logging
import os
import re
from typing import Any

from supabase import Client

from .embeddings import get_embedding_provider
from .logging_utils import log_event


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
            tagged = kb_query().contains("tags", [tag_value]).limit(limit).execute()
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
            text = kb_query().or_(",".join(or_parts)).limit(limit).execute()
            return text.data or []

        text = (
            kb_query()
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
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
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
        meta = {
            "match_count": len(data),
            "top_similarity": top_similarity,
            "min_similarity": min_similarity,
        }
        log_event(
            logging.INFO,
            "kb_vector_matches",
            count=len(data),
            top_similarity=top_similarity,
            min_similarity=min_similarity,
        )
        return data, meta
    except Exception as exc:
        log_event(logging.ERROR, "kb_vector_search_error", error=str(exc))
        return [], None


def retrieve_kb_reply(
    supabase: Client, message: str, org_id: str | None
) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
    limit = int(os.getenv("VECTOR_MATCH_COUNT", "3"))
    min_similarity = float(os.getenv("VECTOR_MIN_SIMILARITY", "0.2"))

    vector_matches, vector_meta = retrieve_kb_vector_matches(
        supabase,
        message,
        org_id,
        limit=limit,
        min_similarity=min_similarity,
    )
    if vector_matches:
        reply, citations = build_kb_chunk_reply(vector_matches[0])
        run_meta: dict[str, Any] = {"retrieval_source": "vector"}
        if vector_meta:
            run_meta.update(vector_meta)
        return reply, citations, 0.9, run_meta

    doc_matches = retrieve_kb_candidates(supabase, message, org_id)
    if doc_matches:
        reply, citations = build_kb_reply(doc_matches[0])
        return (
            reply,
            citations,
            0.85,
            {"retrieval_source": "document", "document_match_count": len(doc_matches)},
        )

    return None
