# SupportOps Roadmap (Internal)

This roadmap tracks the learning-focused agent system work. It is not user-facing.

## Status Summary (Completed)

### Epic 1: Observability base
- Structured logs with retrieval + decision metadata
- `agent_runs` enriched with latency, retrieval_source, decision_source
- Runs UI summary cards (action mix, latency, escalation rate, retrieval source)
- Smoke checks documented

### Epic 2: Decision layer + guardrails
- Guardrail: `reply` requires citations
- Guardrail: `reply` blocked when vector `top_similarity < REPLY_MIN_SIMILARITY`
- Explicit `decision_reason` + guardrail logging
- Action accuracy hooks (`eval_action_result`)
- Conversation context appended for follow-up questions
- Conversation persistence: list recent conversations + rehydrate messages in UI

### Epic 3: Eval Gates (CI)
- Expanded eval set with categories
- Per-category thresholds in `packages/eval/thresholds.json`
- Runner reports category metrics and enforces thresholds
- CI workflow runs `run_eval.py`

## Platform Foundation (Next)

### Epic 4: Core Platform Abstractions (Clean Architecture)
- Introduce repo interfaces: conversations, messages, KB, runs, orgs
- Default adapter: Supabase (current behavior)
- Define service layer (decision + retrieval orchestration)
- DTOs/ports to keep HTTP/DB boundaries clean
- Add integration tests for repo adapters

### Epic 5: Storage Adapter v2 (Postgres-ready)
- Implement Postgres adapter (SQLAlchemy/psycopg) behind repo interfaces
- Move RPC usage behind adapter (match_kb_chunks abstraction)
- Parity test suite: Supabase vs Postgres adapter outputs
- Migration guide for swapping storage

### Epic 6: Retrieval Engine Adapter
- Introduce `Retriever` interface (current RAG vs external engines)
- Adapter 1: existing vector+text retrieval
- Adapter 2: LlamaIndex (optional) for top-k + rerank
- Standardize output: citations + similarity + retrieval_source

### Epic 4b: Adapter Completion (Supabase)
- Migrate remaining endpoints to repo interfaces (KB, tickets, orgs, runs)
- Introduce a retriever adapter wrapper used by the service layer
- Add integration tests for adapters (beyond contract tests)

## Known Limitations

- Chat UI does not yet merge `agent_runs` into message bubbles (actions/confidence only from responses).
- No RLS; org scoping is server-side filters.
- Storage is still Supabase-coupled (repo interfaces pending).
