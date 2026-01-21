create extension if not exists "pgcrypto";
create extension if not exists vector;

create table if not exists orgs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  created_at timestamptz not null default now()
);

create table if not exists members (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id) on delete cascade,
  user_id text not null,
  role text not null check (role in ('admin', 'agent', 'viewer')),
  created_at timestamptz not null default now(),
  unique (org_id, user_id)
);

insert into orgs (name, slug)
values ('Default', 'default')
on conflict (slug) do nothing;

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  org_name text;
  base_slug text;
  final_slug text;
  new_org_id uuid;
begin
  org_name :=
    coalesce(new.raw_user_meta_data->>'org_name', split_part(new.email, '@', 1), 'Workspace');
  base_slug := lower(regexp_replace(org_name, '[^a-z0-9]+', '-', 'g'));
  base_slug := trim(both '-' from base_slug);
  if base_slug is null or base_slug = '' then
    base_slug := 'workspace';
  end if;
  final_slug := left(base_slug, 24) || '-' || substr(replace(gen_random_uuid()::text, '-', ''), 1, 6);

  insert into public.orgs (name, slug)
  values (org_name, final_slug)
  returning id into new_org_id;

  insert into public.members (org_id, user_id, role)
  values (new_org_id, new.id::text, 'admin')
  on conflict (org_id, user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute function public.handle_new_user();

create table if not exists conversations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id) on delete cascade,
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
  org_id uuid not null references orgs(id) on delete cascade,
  conversation_id uuid references conversations(id) on delete set null,
  status text not null default 'open' check (status in ('open', 'waiting_user', 'waiting_team', 'resolved')),
  priority text not null default 'normal' check (priority in ('low', 'normal', 'high')),
  subject text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists kb_documents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id) on delete cascade,
  title text not null,
  content text not null,
  tags text[] not null default '{}'::text[],
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists kb_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references kb_documents(id) on delete cascade,
  org_id uuid not null references orgs(id) on delete cascade,
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
  org_id uuid not null references orgs(id) on delete cascade,
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
  query_embedding jsonb,
  match_count int default 5,
  min_similarity float default 0.2,
  p_org_id uuid default null
)
returns table (
  id uuid,
  document_id uuid,
  org_id uuid,
  chunk_index int,
  content text,
  document_title text,
  similarity float
)
language sql stable
as $$
  with query as (
    select array_agg(value::float4) as vec
    from jsonb_array_elements_text(query_embedding) as t(value)
  )
  select
    kc.id,
    kc.document_id,
    kc.org_id,
    kc.chunk_index,
    kc.content,
    kd.title as document_title,
    1 - (kc.embedding <=> query.vec::vector) as similarity
  from kb_chunks kc
  join kb_documents kd on kd.id = kc.document_id
  cross join query
  where kc.embedding is not null
    and query.vec is not null
    and (p_org_id is null or kc.org_id = p_org_id)
    and 1 - (kc.embedding <=> query.vec::vector) >= min_similarity
  order by kc.embedding <=> query.vec::vector
  limit match_count;
$$;

create index if not exists messages_conversation_created_idx on messages(conversation_id, created_at);
create index if not exists tickets_conversation_id_idx on tickets(conversation_id);
create index if not exists kb_documents_org_id_idx on kb_documents(org_id);
create index if not exists kb_documents_tags_idx on kb_documents using gin (tags);
create index if not exists kb_chunks_org_id_idx on kb_chunks(org_id);
create index if not exists kb_chunks_document_id_idx on kb_chunks(document_id);
create index if not exists kb_chunks_embedding_idx on kb_chunks using ivfflat (embedding vector_cosine_ops) where embedding is not null;
create unique index if not exists kb_chunks_document_hash_idx on kb_chunks(document_id, chunk_hash) where chunk_hash is not null;
create index if not exists conversations_org_id_idx on conversations(org_id);
create index if not exists tickets_org_id_idx on tickets(org_id);
create index if not exists agent_runs_org_id_idx on agent_runs(org_id);
create index if not exists agent_runs_conversation_created_idx on agent_runs(conversation_id, created_at);
