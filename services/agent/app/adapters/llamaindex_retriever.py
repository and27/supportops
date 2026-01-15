from __future__ import annotations

import logging
from typing import Any

from ..logging_utils import log_event
from ..ports import Retriever

try:
    from llama_index.core import Document, VectorStoreIndex
except Exception:  # pragma: no cover - optional dependency
    Document = None
    VectorStoreIndex = None


class LlamaIndexRetriever(Retriever):
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        if Document is None or VectorStoreIndex is None:
            raise RuntimeError("llama_index_not_installed")
        self._index = VectorStoreIndex.from_documents(
            [Document(text=doc.get("content", ""), doc_id=doc.get("id")) for doc in documents]
        )

    def retrieve(
        self, message: str, org_id: str | None
    ) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
        try:
            retriever = self._index.as_retriever(similarity_top_k=3)
            nodes = retriever.retrieve(message)
        except Exception as exc:
            log_event(logging.ERROR, "llamaindex_retrieval_error", error=str(exc))
            return None
        if not nodes:
            return None
        top = nodes[0]
        reply = top.text if hasattr(top, "text") else ""
        citations = [{"kb_document_id": getattr(top, "node_id", "")}]
        return reply, citations, 0.85, {"retrieval_source": "llamaindex"}
