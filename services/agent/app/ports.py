from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConversationsRepo(Protocol):
    def create_conversation(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None: ...

    def list_conversations(self, org_id: str, limit: int) -> list[dict[str, Any]]: ...


@runtime_checkable
class MessagesRepo(Protocol):
    def create_message(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def list_messages(
        self, conversation_id: str, limit: int
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class TicketsRepo(Protocol):
    def create_ticket(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def list_tickets(self, org_id: str, limit: int) -> list[dict[str, Any]]: ...

    def get_ticket(self, ticket_id: str) -> dict[str, Any] | None: ...


@runtime_checkable
class KBRepo(Protocol):
    def create_document(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def update_document(
        self, document_id: str, data: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    def delete_document(self, document_id: str) -> bool: ...

    def get_document(self, document_id: str) -> dict[str, Any] | None: ...

    def list_documents(self, org_id: str, limit: int) -> list[dict[str, Any]]: ...

    def search_by_tags(
        self, org_id: str, tags: list[str], limit: int
    ) -> list[dict[str, Any]]: ...

    def search_by_text(
        self, org_id: str, query: str, limit: int
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class KBChunksRepo(Protocol):
    def list_chunks(self, document_id: str) -> list[dict[str, Any]]: ...

    def delete_chunks(self, chunk_ids: list[str]) -> None: ...

    def insert_chunks(self, rows: list[dict[str, Any]]) -> None: ...


@runtime_checkable
class RunsRepo(Protocol):
    def create_run(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def list_runs(self, org_id: str, limit: int) -> list[dict[str, Any]]: ...

    def get_run(self, run_id: str) -> dict[str, Any] | None: ...

    def list_runs_for_conversation(
        self, org_id: str, conversation_id: str, limit: int
    ) -> list[dict[str, Any]]: ...


@runtime_checkable
class OrgsRepo(Protocol):
    def list_orgs(self, limit: int) -> list[dict[str, Any]]: ...

    def create_org(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def get_org(self, org_id: str) -> dict[str, Any] | None: ...

    def get_org_by_slug(self, slug: str) -> dict[str, Any] | None: ...


@runtime_checkable
class MembersRepo(Protocol):
    def list_members(self, org_id: str, limit: int) -> list[dict[str, Any]]: ...

    def create_member(self, data: dict[str, Any]) -> dict[str, Any]: ...

    def get_member_role(self, org_id: str, user_id: str) -> str | None: ...

    def list_memberships(self, user_id: str) -> list[dict[str, Any]]: ...


@runtime_checkable
class Retriever(Protocol):
    def retrieve(
        self, message: str, org_id: str | None, trace_id: str | None = None
    ) -> tuple[str, list[dict[str, Any]], float, dict[str, Any]] | None: ...
