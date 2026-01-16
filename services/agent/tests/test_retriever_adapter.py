import unittest
from unittest.mock import patch

from app.adapters.retriever_adapter import DefaultRetriever, get_retriever


class StubKBRepo:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search_by_tags(self, org_id: str, tags: list[str], limit: int):
        self.calls.append("search_by_tags")
        return []

    def search_by_text(self, org_id: str, query: str, limit: int):
        self.calls.append("search_by_text")
        return [{"id": "k1", "title": "KB", "content": "Details"}]


class RetrieverAdapterTests(unittest.TestCase):
    def test_retriever_uses_kb_repo(self) -> None:
        supabase = object()
        kb_repo = StubKBRepo()
        retriever = DefaultRetriever(supabase, kb_repo)

        with patch.dict("os.environ", {"VECTOR_SEARCH_ENABLED": "false"}, clear=False):
            result = retriever.retrieve("integration docs", "org1")

        self.assertIsNotNone(result)
        self.assertIn("search_by_text", kb_repo.calls)

    def test_llamaindex_engine_falls_back(self) -> None:
        supabase = object()
        kb_repo = StubKBRepo()
        with patch.dict("os.environ", {"RETRIEVER_ENGINE": "llamaindex"}, clear=False):
            retriever = get_retriever(supabase, kb_repo)

        self.assertIsInstance(retriever, DefaultRetriever)


if __name__ == "__main__":
    unittest.main()
