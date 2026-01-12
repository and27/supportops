create extension if not exists "pgcrypto";

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
  metadata jsonb,
  created_at timestamptz not null default now()
);

create index if not exists messages_conversation_created_idx on messages(conversation_id, created_at);
create index if not exists tickets_conversation_id_idx on tickets(conversation_id);
create index if not exists kb_documents_tags_idx on kb_documents using gin (tags);
create index if not exists kb_chunks_document_id_idx on kb_chunks(document_id);
