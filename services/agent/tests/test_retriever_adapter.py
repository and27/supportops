import unittest
from unittest.mock import patch

from app.adapters.retriever_adapter import DefaultRetriever


class RetrieverAdapterTests(unittest.TestCase):
    def test_retriever_delegates_to_kb_retrieval(self) -> None:
        supabase = object()
        expected = ("reply", [{"kb_document_id": "k1"}], 0.9, {"source": "kb"})
        with patch(
            "app.adapters.retriever_adapter.retrieve_kb_reply",
            return_value=expected,
        ) as mocked:
            retriever = DefaultRetriever(supabase)

            result = retriever.retrieve("hello", "org1")

            self.assertEqual(result, expected)
            mocked.assert_called_once_with(supabase, "hello", "org1")


if __name__ == "__main__":
    unittest.main()
