create extension if not exists vector;

alter table kb_chunks
  add column if not exists embedding vector(1536),
  add column if not exists embedding_model text;

create table if not exists agent_runs (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete set null,
  message_id uuid references messages(id) on delete set null,
  action text not null check (action in ('reply', 'ask_clarifying', 'create_ticket', 'escalate')),
  confidence numeric,
  input jsonb,
  output jsonb,
  citations jsonb,
  model text,
  prompt_tokens integer,
  completion_tokens integer,
  total_tokens integer,
  latency_ms integer,
  cost_usd numeric,
  metadata jsonb,
  created_at timestamptz not null default now()
);

create index if not exists kb_chunks_embedding_idx on kb_chunks using ivfflat (embedding vector_cosine_ops) where embedding is not null;
create index if not exists agent_runs_conversation_created_idx on agent_runs(conversation_id, created_at);
