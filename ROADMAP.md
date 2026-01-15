# SupportOps Roadmap (Internal)

This roadmap tracks the learning-focused agent system work. It is not user-facing.

## Status Summary

### Completed
- Epic 1: Observability base
  - Structured logs with retrieval + decision metadata
  - `agent_runs` enriched with latency, retrieval_source, decision_source
  - Runs UI summary cards (action mix, latency, escalation rate, retrieval source)
  - Smoke checks documented
- Epic 2: Decision layer + guardrails
  - Guardrail: `reply` requires citations
  - Guardrail: `reply` blocked when vector `top_similarity < REPLY_MIN_SIMILARITY`
  - Explicit `decision_reason` + guardrail logging
  - Action accuracy hooks (`eval_action_result`)
  - Conversation context appended for follow-up questions
  - Conversation persistence: list recent conversations + rehydrate messages in UI
- Epic 3: Eval Gates (CI)
  - Expanded eval set with categories
  - Per-category thresholds in `packages/eval/thresholds.json`
  - Runner reports category metrics and enforces thresholds
  - CI workflow runs `run_eval.py`

## In Progress / Next

### Epic 4: Retrieval v2 (Top-k + Thresholds)
- Parameterize per org: `VECTOR_MATCH_COUNT`, `VECTOR_MIN_SIMILARITY`, `REPLY_MIN_SIMILARITY`
- A/B compare configs (citation relevance + action accuracy + escalation rate)
- Logging dashboard for threshold experiments

### Epic 5: Reranking (later)
- Add labeled data for hit@k/MRR
- Implement reranking and compare vs baseline

## Known Limitations

- Chat UI does not yet merge `agent_runs` into message bubbles (actions/confidence only from responses).
- No RLS; org scoping is server‑side filters.
- Eval suite still uses a small seed set; no CI gate yet.
