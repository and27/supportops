from __future__ import annotations

from typing import Any

from ..ports import Retriever
from ..retrieval import retrieve_kb_reply


class DefaultRetriever(Retriever):
    def __init__(self, supabase) -> None:
        self._supabase = supabase

    def retrieve(
        self, message: str, org_id: str | None
    ) -> tuple[str, list[dict[str, str]], float, dict[str, Any]] | None:
        return retrieve_kb_reply(self._supabase, message, org_id)


def get_retriever(supabase) -> Retriever:
    return DefaultRetriever(supabase)
