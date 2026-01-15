import types
import unittest

from app.adapters.supabase_repos import (
    SupabaseConversationsRepo,
    SupabaseKBRepo,
    SupabaseMessagesRepo,
)


class StubTable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[tuple[str, object]] = []
        self._result_data: list[dict] = []

    def insert(self, data):
        self.calls.append(("insert", data))
        return self

    def update(self, data):
        self.calls.append(("update", data))
        return self

    def select(self, *args):
        self.calls.append(("select", args))
        return self

    def eq(self, key, value):
        self.calls.append(("eq", (key, value)))
        return self

    def order(self, *args, **kwargs):
        self.calls.append(("order", (args, kwargs)))
        return self

    def limit(self, value):
        self.calls.append(("limit", value))
        return self

    def contains(self, key, value):
        self.calls.append(("contains", (key, value)))
        return self

    def or_(self, value):
        self.calls.append(("or_", value))
        return self

    def execute(self):
        return types.SimpleNamespace(data=self._result_data)


class StubSupabase:
    def __init__(self) -> None:
        self.tables: dict[str, StubTable] = {}

    def table(self, name: str) -> StubTable:
        if name not in self.tables:
            self.tables[name] = StubTable(name)
        return self.tables[name]


class SupabaseReposContractTests(unittest.TestCase):
    def test_create_conversation_returns_row(self) -> None:
        supabase = StubSupabase()
        table = supabase.table("conversations")
        table._result_data = [{"id": "c1"}]
        repo = SupabaseConversationsRepo(supabase)

        row = repo.create_conversation({"id": "c1"})

        self.assertEqual(row["id"], "c1")
        self.assertIn(("insert", {"id": "c1"}), table.calls)

    def test_list_conversations_filters_org(self) -> None:
        supabase = StubSupabase()
        table = supabase.table("conversations")
        table._result_data = [{"id": "c1"}]
        repo = SupabaseConversationsRepo(supabase)

        rows = repo.list_conversations("org1", 10)

        self.assertEqual(len(rows), 1)
        self.assertIn(("eq", ("org_id", "org1")), table.calls)

    def test_messages_list_orders_and_limits(self) -> None:
        supabase = StubSupabase()
        table = supabase.table("messages")
        table._result_data = [{"id": "m1"}]
        repo = SupabaseMessagesRepo(supabase)

        rows = repo.list_messages("c1", 25)

        self.assertEqual(len(rows), 1)
        self.assertIn(("eq", ("conversation_id", "c1")), table.calls)
        self.assertTrue(any(call[0] == "order" for call in table.calls))
        self.assertIn(("limit", 25), table.calls)

    def test_kb_search_by_tags_uses_contains(self) -> None:
        supabase = StubSupabase()
        table = supabase.table("kb_documents")
        table._result_data = [{"id": "k1"}]
        repo = SupabaseKBRepo(supabase)

        rows = repo.search_by_tags("org1", ["billing"], 3)

        self.assertEqual(len(rows), 1)
        self.assertIn(("contains", ("tags", ["billing"])), table.calls)

    def test_kb_search_by_text_uses_or(self) -> None:
        supabase = StubSupabase()
        table = supabase.table("kb_documents")
        table._result_data = [{"id": "k1"}]
        repo = SupabaseKBRepo(supabase)

        rows = repo.search_by_text("org1", "reset", 3)

        self.assertEqual(len(rows), 1)
        self.assertTrue(any(call[0] == "or_" for call in table.calls))


if __name__ == "__main__":
    unittest.main()
