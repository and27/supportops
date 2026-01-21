from __future__ import annotations

from typing import Any


def select_chunks(
    matches: list[dict[str, Any]],
    max_chunks: int,
    max_per_doc: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    per_doc: dict[str, int] = {}

    for row in matches:
        chunk_id = str(row.get("id") or "")
        if not chunk_id or chunk_id in seen_chunks:
            continue
        doc_id = str(row.get("document_id") or "")
        if doc_id and per_doc.get(doc_id, 0) >= max_per_doc:
            continue
        selected.append(row)
        seen_chunks.add(chunk_id)
        if doc_id:
            per_doc[doc_id] = per_doc.get(doc_id, 0) + 1
        if len(selected) >= max_chunks:
            break

    return selected


def build_citations(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for chunk in chunks:
        citation: dict[str, Any] = {
            "kb_chunk_id": chunk.get("id"),
            "kb_document_id": chunk.get("document_id"),
        }
        title = chunk.get("document_title")
        if title:
            citation["source"] = title
        similarity = chunk.get("similarity")
        if isinstance(similarity, (int, float)):
            citation["score"] = similarity
        citations.append(citation)
    return citations
