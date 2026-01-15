# Telemetry

Canonical telemetry for the agent runtime. Use these events for dashboards and alerts.

## Canonical events

All canonical events include:
- conversation_id
- tenant_id (org_id)
- channel

### request_started
- input_length_chars

### retrieval_done
- retrieval_ms
- retrieval_candidates_count
- top_similarity
- retrieval_source

### decision_made
- decision (reply|ask_clarifying|handoff)
- decision_reason (always set; defaults to `unspecified`)
- guardrails_triggered (array)
- has_citations
- handoff_type (create_ticket|escalate when decision=handoff)

### reply_sent
- response_tokens_estimated
- latency_ms_total

### handoff_sent
- response_tokens_estimated
- latency_ms_total
- handoff_type

## Notes

- response_tokens_estimated uses chars/4 and rounds down.
- Legacy chat_request and chat_response remain for compatibility.
- Client IP is not logged in canonical events.
