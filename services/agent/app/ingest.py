import logging
import os
from hashlib import sha256

from fastapi import HTTPException
from supabase import Client

from .embeddings import EmbeddingProvider
from .logging_utils import log_event
from .schemas import IngestResponse


def chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    size = max(1, min(chunk_size, 400))
    overlap = max(0, min(chunk_overlap, size - 1))

    chunks = []
    start = 0
    while start < len(words):
        end = min(len(words), start + size)
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(words):
            break
        start = max(0, end - overlap)
    return chunks


def hash_chunk(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def get_ingest_config() -> tuple[int, int, bool]:
    chunk_size = int(os.getenv("INGEST_CHUNK_SIZE", "120"))
    chunk_overlap = int(os.getenv("INGEST_CHUNK_OVERLAP", "20"))
    auto_ingest = os.getenv("AUTO_INGEST_ON_KB_WRITE", "false").lower() == "true"
    return chunk_size, chunk_overlap, auto_ingest


def run_ingest(
    supabase: Client,
    provider: EmbeddingProvider,
    document_id: str,
    org_id: str | None,
    chunk_size: int,
    chunk_overlap: int,
    force: bool,
) -> IngestResponse:
    log_event(
        logging.INFO,
        "ingest_start",
        document_id=document_id,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        force=force,
    )

    try:
        query = supabase.table("kb_documents").select("*").eq("id", document_id)
        if org_id:
            query = query.eq("org_id", org_id)
        doc_result = query.limit(1).execute()
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    if not doc_result.data:
        raise HTTPException(status_code=404, detail="kb_not_found")

    document = doc_result.data[0]
    doc_org_id = document.get("org_id")
    if not doc_org_id:
        log_event(logging.ERROR, "kb_missing_org", document_id=document_id)
        raise HTTPException(status_code=500, detail="kb_missing_org")
    chunks = chunk_text(document.get("content", ""), chunk_size, chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=400, detail="kb_content_empty")

    chunk_hashes = [hash_chunk(chunk) for chunk in chunks]
    unique_map: dict[str, int] = {}
    unique_chunks: list[str] = []
    for index, chunk_hash in enumerate(chunk_hashes):
        if chunk_hash in unique_map:
            continue
        unique_map[chunk_hash] = index
        unique_chunks.append(chunks[index])

    try:
        existing = (
            supabase.table("kb_chunks")
            .select("id,chunk_hash")
            .eq("document_id", document_id)
            .execute()
        )
    except Exception as exc:
        log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
        raise HTTPException(status_code=500, detail="db_error")

    existing_hashes = {
        row.get("chunk_hash"): row.get("id")
        for row in (existing.data or [])
        if row.get("chunk_hash")
    }
    new_hashes = set(unique_map.keys())

    chunks_deleted = 0
    if not force:
        to_delete = [
            row_id for chash, row_id in existing_hashes.items() if chash not in new_hashes
        ]
    else:
        to_delete = [row_id for row_id in existing_hashes.values()]

    if to_delete:
        try:
            supabase.table("kb_chunks").delete().in_("id", to_delete).execute()
            chunks_deleted = len(to_delete)
        except Exception as exc:
            log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    if force:
        existing_hashes = {}

    to_insert_hashes = [chash for chash in unique_map.keys() if chash not in existing_hashes]
    to_insert_chunks = [chunks[unique_map[chash]] for chash in to_insert_hashes]

    chunks_inserted = 0
    if to_insert_chunks:
        try:
            embeddings = provider.embed(to_insert_chunks)
        except Exception as exc:
            log_event(logging.ERROR, "embedding_error", error=str(exc))
            raise HTTPException(status_code=500, detail="embedding_error")

        rows = []
        for chash, chunk, embedding in zip(to_insert_hashes, to_insert_chunks, embeddings):
            rows.append(
                {
                    "document_id": document_id,
                    "org_id": doc_org_id,
                    "chunk_index": unique_map[chash],
                    "content": chunk,
                    "chunk_hash": chash,
                    "embedding": embedding,
                    "embedding_model": provider.model,
                    "embedding_version": provider.version,
                }
            )
        try:
            supabase.table("kb_chunks").insert(rows).execute()
            chunks_inserted = len(rows)
        except Exception as exc:
            log_event(logging.ERROR, "db_error", doc_id=document_id, error=str(exc))
            raise HTTPException(status_code=500, detail="db_error")

    chunks_total = len(unique_chunks)
    chunks_skipped = chunks_total - chunks_inserted

    log_event(
        logging.INFO,
        "ingest_complete",
        document_id=document_id,
        chunks_total=chunks_total,
        chunks_inserted=chunks_inserted,
        chunks_skipped=chunks_skipped,
        chunks_deleted=chunks_deleted,
    )

    return IngestResponse(
        document_id=document_id,
        chunks_total=chunks_total,
        chunks_inserted=chunks_inserted,
        chunks_skipped=chunks_skipped,
        chunks_deleted=chunks_deleted,
        embedding_model=provider.model,
        embedding_version=provider.version,
    )
