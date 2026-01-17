from __future__ import annotations

import logging
import os
from typing import Any

from ..answer_generator import generate_answer
from ..embeddings import get_embedding_provider
from ..logging_utils import log_event
from ..ports import KBRepo, Retriever
from ..retrieval import (
    build_kb_chunk_reply,
    build_kb_reply,
    extract_hash_tags,
    extract_keywords,
)
from ..retrieval_selector import build_citations, select_chunks


class DefaultRetriever(Retriever):
    def __init__(self, supabase, kb_repo: KBRepo) -> None:
        self._supabase = supabase
        self._kb_repo = kb_repo

    def retrieve(
        self, message: str, org_id: str | None, trace_id: str | None = None
    ) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
        query = message.strip().replace(",", " ")
        if not query:
            return None

        tags = extract_hash_tags(query)
        if tags:
            tag_value = tags[0]
            tagged = self._kb_repo.search_by_tags(org_id or "", [tag_value], 3)
            log_event(
                logging.INFO,
                "kb_tag_lookup",
                tag=tag_value,
                org_id=org_id,
                match_count=len(tagged),
            )
            if tagged:
                reply, citations = build_kb_reply(tagged[0])
                return (
                    reply,
                    citations,
                    0.85,
                    {"retrieval_source": "document", "document_match_count": len(tagged)},
                )

        vector_result = self._retrieve_vector(query, org_id, trace_id)
        if vector_result:
            return vector_result

        keywords = extract_keywords(query)
        if keywords:
            or_query = " ".join(keywords)
            docs = self._kb_repo.search_by_text(org_id or "", or_query, 3)
            if docs:
                reply, citations = build_kb_reply(docs[0])
                return (
                    reply,
                    citations,
                    0.85,
                    {
                        "retrieval_source": "document",
                        "document_match_count": len(docs),
                    },
                )

        docs = self._kb_repo.search_by_text(org_id or "", query, 3)
        if docs:
            reply, citations = build_kb_reply(docs[0])
            return (
                reply,
                citations,
                0.85,
                {"retrieval_source": "document", "document_match_count": len(docs)},
            )

        return None

    def _retrieve_vector(
        self, query: str, org_id: str | None, trace_id: str | None
    ) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
        enabled = os.getenv("VECTOR_SEARCH_ENABLED", "false").lower() == "true"
        if not enabled:
            return None

        try:
            provider = get_embedding_provider()
        except RuntimeError as exc:
            log_event(logging.WARNING, "embedding_not_configured", error=str(exc))
            return None

        try:
            limit = int(os.getenv("VECTOR_MATCH_COUNT", "10"))
            min_similarity = float(os.getenv("VECTOR_MIN_SIMILARITY", "0.2"))
            embedding = provider.embed([query])[0]
            result = (
                self._supabase.rpc(
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
            similarities = [
                row.get("similarity")
                for row in data
                if isinstance(row.get("similarity"), (int, float))
            ]
            top_similarity = max(similarities) if similarities else None
            p50 = percentile(similarities, 50)
            p90 = percentile(similarities, 90)
            log_event(
                logging.INFO,
                "kb_vector_matches",
                count=len(data),
                top_similarity=top_similarity,
                similarity_p50=p50,
                similarity_p90=p90,
                min_similarity=min_similarity,
            )
            if not data:
                return None
            max_chunks = int(os.getenv("RETRIEVAL_MAX_CHUNKS", "4"))
            max_per_doc = int(os.getenv("RETRIEVAL_MAX_PER_DOC", "2"))
            selected = select_chunks(data, max_chunks=max_chunks, max_per_doc=max_per_doc)
            if not selected:
                return None
            citations = build_citations(selected)
            reply, confidence, generation_meta = generate_answer(
                query,
                selected,
                org_id,
                trace_id,
            )
            meta = {
                "retrieval_source": "vector",
                "match_count": len(data),
                "selected_count": len(selected),
                "top_similarity": top_similarity,
                "similarity_p50": p50,
                "similarity_p90": p90,
                "min_similarity": min_similarity,
            }
            meta.update(generation_meta)
            return reply, citations, confidence, meta
        except Exception as exc:
            log_event(logging.ERROR, "kb_vector_search_error", error=str(exc))
            return None


def get_retriever(supabase, kb_repo: KBRepo) -> Retriever:
    engine = os.getenv("RETRIEVER_ENGINE", "default").lower()
    if engine and engine != "default":
        log_event(logging.WARNING, "retriever_engine_deprecated", engine=engine)
    return DefaultRetriever(supabase, kb_repo)


def percentile(values: list[float], pct: int) -> float | None:
    if not values:
        return None
    if pct <= 0:
        return min(values)
    if pct >= 100:
        return max(values)
    sorted_values = sorted(values)
    index = int(round((pct / 100) * (len(sorted_values) - 1)))
    return sorted_values[index]
