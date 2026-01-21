import unittest
from unittest.mock import patch

from app.schemas import ChatRequest
from app.service import ChatDependencies, handle_chat


class StubConversationsRepo:
    def __init__(self) -> None:
        self.created = []

    def create_conversation(self, data):
        self.created.append(data)
        return data


class StubMessagesRepo:
    def __init__(self) -> None:
        self.created = []

    def list_messages(self, conversation_id, limit):
        return []

    def create_message(self, data):
        self.created.append(data)
        return data


class StubTicketsRepo:
    def create_ticket(self, data):
        return {"id": "t1"}


class StubRunsRepo:
    def __init__(self) -> None:
        self.created = []

    def create_run(self, data):
        self.created.append(data)
        return data


class ReplyRetriever:
    def __init__(self, citations):
        self._citations = citations

    def retrieve(self, message, org_id, trace_id=None):
        return (
            "Here is the answer.",
            self._citations,
            0.9,
            {
                "retrieval_source": "vector",
                "match_count": 1,
                "top_similarity": 0.9,
            },
        )


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.org_id = "org1"
        self.payload = ChatRequest(
            message="I need help resetting my account password please.",
            channel="web",
        )

    def test_reply_with_citations(self):
        deps = ChatDependencies(
            conversations_repo=StubConversationsRepo(),
            messages_repo=StubMessagesRepo(),
            tickets_repo=StubTicketsRepo(),
            runs_repo=StubRunsRepo(),
            retriever=ReplyRetriever([{"kb_document_id": "doc1"}]),
        )
        response = handle_chat(self.payload, self.org_id, None, deps)
        self.assertEqual(response.action, "reply")
        self.assertTrue(response.citations)
        self.assertEqual(len(deps.messages_repo.created), 2)

    def test_missing_citations_triggers_clarify(self):
        deps = ChatDependencies(
            conversations_repo=StubConversationsRepo(),
            messages_repo=StubMessagesRepo(),
            tickets_repo=StubTicketsRepo(),
            runs_repo=StubRunsRepo(),
            retriever=ReplyRetriever(None),
        )
        with patch.dict("os.environ", {"REPLY_MIN_SIMILARITY": "0.0"}, clear=False):
            response = handle_chat(self.payload, self.org_id, None, deps)
        self.assertEqual(response.action, "ask_clarifying")
        self.assertIsNone(response.citations)


if __name__ == "__main__":
    unittest.main()
