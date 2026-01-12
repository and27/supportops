create extension if not exists "pgcrypto";
create extension if not exists vector;

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  channel text not null default 'web',
  metadata jsonb,
  created_at timestamptz not null default now()
);

create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references conversations(id) on delete cascade,
  role text not null check (role in ('user', 'assistant', 'system')),
  content text not null,
  metadata jsonb,
  created_at timestamptz not null default now()
);

create table if not exists tickets (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid references conversations(id) on delete set null,
  status text not null default 'open' check (status in ('open', 'waiting_user', 'waiting_team', 'resolved')),
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
  subject text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists kb_documents (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  content text not null,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists kb_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references kb_documents(id) on delete cascade,
  chunk_index integer not null,
  content text not null,
  chunk_hash text,
  embedding vector(1536),
  embedding_model text,
  embedding_version text,
  metadata jsonb,
  created_at timestamptz not null default now()
);

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

create or replace function match_kb_chunks(
  query_embedding vector(1536),
  match_count int default 5,
  min_similarity float default 0.2
)
returns table (
  id uuid,
  document_id uuid,
  chunk_index int,
  content text,
  document_title text,
  similarity float
)
language sql stable
as $$
  select
    kc.id,
    kc.document_id,
    kc.chunk_index,
    kc.content,
    kd.title as document_title,
    1 - (kc.embedding <=> query_embedding) as similarity
  from kb_chunks kc
  join kb_documents kd on kd.id = kc.document_id
  where kc.embedding is not null
    and 1 - (kc.embedding <=> query_embedding) >= min_similarity
  order by kc.embedding <=> query_embedding
  limit match_count;
$$;

create index if not exists messages_conversation_created_idx on messages(conversation_id, created_at);
create index if not exists tickets_conversation_id_idx on tickets(conversation_id);
create index if not exists kb_documents_tags_idx on kb_documents using gin (tags);
create index if not exists kb_chunks_document_id_idx on kb_chunks(document_id);
create index if not exists kb_chunks_embedding_idx on kb_chunks using ivfflat (embedding vector_cosine_ops) where embedding is not null;
create unique index if not exists kb_chunks_document_hash_idx on kb_chunks(document_id, chunk_hash) where chunk_hash is not null;
create index if not exists agent_runs_conversation_created_idx on agent_runs(conversation_id, created_at);
