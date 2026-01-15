# Architecture Notes

This repo is moving toward a ports/adapters (clean) architecture. The agent
runtime should orchestrate decisions while storage and retrieval are pluggable.

## Boundaries

- **API layer**: FastAPI routes accept HTTP and map to service calls.
- **Service layer**: decision + retrieval orchestration. No direct DB calls.
- **Ports**: repo + retriever interfaces (`services/agent/app/ports.py`).
- **Adapters**: Supabase implementation today; Postgres adapter later.

## Current Ports (v4 foundation)

- `ConversationsRepo`
- `MessagesRepo`
- `TicketsRepo`
- `KBRepo`
- `RunsRepo`
- `OrgsRepo`
- `MembersRepo`
- `Retriever`

## Contract Rules

- Service layer returns plain data dicts (no DB client objects).
- Adapters may use DB-specific features, but must keep outputs consistent.
- Retrieval returns `(reply, citations, confidence, metadata)` as a stable tuple.
