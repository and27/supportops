from __future__ import annotations

from typing import Any

from supabase import Client

from ..ports import (
    ConversationsRepo,
    KBChunksRepo,
    KBRepo,
    MembersRepo,
    MessagesRepo,
    OrgsRepo,
    RunsRepo,
    TicketsRepo,
)


class SupabaseConversationsRepo(ConversationsRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def create_conversation(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("conversations").insert(data).execute()
        return (result.data or [data])[0]

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("conversations")
            .select("*")
            .eq("id", conversation_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_conversations(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("conversations")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


class SupabaseMessagesRepo(MessagesRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def create_message(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("messages").insert(data).execute()
        return (result.data or [data])[0]

    def list_messages(
        self, conversation_id: str, limit: int
    ) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("messages")
            .select("id,conversation_id,role,content,metadata,created_at")
            .eq("conversation_id", conversation_id)
            .order("created_at")
            .limit(limit)
            .execute()
        )
        return result.data or []


class SupabaseTicketsRepo(TicketsRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def create_ticket(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("tickets").insert(data).execute()
        return (result.data or [data])[0]

    def list_tickets(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("tickets")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("tickets")
            .select("*")
            .eq("id", ticket_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None


class SupabaseKBRepo(KBRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def create_document(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("kb_documents").insert(data).execute()
        return (result.data or [data])[0]

    def update_document(
        self, document_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        result = (
            self._supabase.table("kb_documents")
            .update(data)
            .eq("id", document_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_document(self, document_id: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("kb_documents")
            .select("*")
            .eq("id", document_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_documents(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("kb_documents")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def search_by_tags(
        self, org_id: str, tags: list[str], limit: int
    ) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("kb_documents")
            .select("*")
            .eq("org_id", org_id)
            .contains("tags", tags)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def search_by_text(
        self, org_id: str, query: str, limit: int
    ) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("kb_documents")
            .select("*")
            .eq("org_id", org_id)
            .or_(f"title.ilike.%{query}%,content.ilike.%{query}%")
            .limit(limit)
            .execute()
        )
        return result.data or []


class SupabaseKBChunksRepo(KBChunksRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def list_chunks(self, document_id: str) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("kb_chunks")
            .select("id,chunk_hash")
            .eq("document_id", document_id)
            .execute()
        )
        return result.data or []

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        self._supabase.table("kb_chunks").delete().in_("id", chunk_ids).execute()

    def insert_chunks(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        self._supabase.table("kb_chunks").insert(rows).execute()


class SupabaseRunsRepo(RunsRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def create_run(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("agent_runs").insert(data).execute()
        return (result.data or [data])[0]

    def list_runs(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("agent_runs")
            .select("*")
            .eq("org_id", org_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("agent_runs")
            .select("*")
            .eq("id", run_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def list_runs_for_conversation(
        self, org_id: str, conversation_id: str, limit: int
    ) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("agent_runs")
            .select("*")
            .eq("org_id", org_id)
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []


class SupabaseOrgsRepo(OrgsRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def list_orgs(self, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("orgs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def create_org(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("orgs").insert(data).execute()
        return (result.data or [data])[0]

    def get_org(self, org_id: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("orgs")
            .select("*")
            .eq("id", org_id)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None

    def get_org_by_slug(self, slug: str) -> dict[str, Any] | None:
        result = (
            self._supabase.table("orgs")
            .select("*")
            .eq("slug", slug)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None


class SupabaseMembersRepo(MembersRepo):
    def __init__(self, supabase: Client) -> None:
        self._supabase = supabase

    def list_members(self, org_id: str, limit: int) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("members")
            .select("*")
            .eq("org_id", org_id)
            .limit(limit)
            .execute()
        )
        return result.data or []

    def create_member(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._supabase.table("members").insert(data).execute()
        return (result.data or [data])[0]

    def get_member_role(self, org_id: str, user_id: str) -> str | None:
        result = (
            self._supabase.table("members")
            .select("role")
            .eq("org_id", org_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0].get("role")

    def list_memberships(self, user_id: str) -> list[dict[str, Any]]:
        result = (
            self._supabase.table("members")
            .select("org_id, role")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data or []
