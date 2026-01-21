# SupportOps Roadmap (Internal)

This roadmap tracks the learning-focused agent system work. It is not user-facing.

## Status Summary

### Completed

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

### In Progress

#### Epic 4: Core Platform Abstractions (Clean Architecture)
- Repo interfaces: conversations, messages, KB, runs, orgs
- Default adapter: Supabase
- Adapter contract tests
- Pending: extract service layer from `main.py` into a dedicated module

#### Epic 5: Storage Adapter Neutrality
- Remaining direct Supabase usage moved into adapters
- Supabase remains default implementation
- Pending: complete service-layer isolation to keep HTTP/DB boundaries clean

#### Epic 6: RAG v2 (Vector-only, incremental, multi-tenant)
- Removed LlamaIndex adapter + dependency (vector-only path)
- Vector retrieval via `match_kb_chunks` (top_k default 10)
- Selector: dedupe + diversity + 2-4 chunks max
- LLM answer generation from selected chunks with structured citations
- Standardize retriever output: reply + citations + confidence + meta
- Telemetry for retrieval/generation timings + top_similarity distribution
- Ensure RPC returns `org_id` for strict multi-tenant filtering
- Optional rerank (listwise) behind feature flag + similarity heuristics
- Tests: selector, rerank fallback, generation fallback

## Next Steps (Current Focus)

1) Extract service layer from `services/agent/app/main.py`
   - New module for decision + retrieval orchestration
   - `main.py` becomes router + dependency injection only
   - Add unit tests for service functions
2) Finish RAG v2 safeguards
   - Optional rerank gating thresholds (if enabled)
   - Retrieval quality tuning (per-tenant thresholds)

## Known Limitations

- Chat UI does not yet merge `agent_runs` into message bubbles (actions/confidence only from responses).
- No RLS; org scoping is server-side filters.
- Storage is still Supabase-coupled (repo interfaces pending).
