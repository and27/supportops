import os
import unittest

from app.adapters.retriever_adapter import DefaultRetriever


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

        os.environ["VECTOR_SEARCH_ENABLED"] = "false"
        result = retriever.retrieve("integration docs", "org1")

        self.assertIsNotNone(result)
        self.assertIn("search_by_text", kb_repo.calls)


if __name__ == "__main__":
    unittest.main()
