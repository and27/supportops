alter table kb_documents add column if not exists org_id uuid;
alter table kb_chunks add column if not exists org_id uuid;
alter table conversations add column if not exists org_id uuid;
alter table tickets add column if not exists org_id uuid;
alter table agent_runs add column if not exists org_id uuid;

with default_org as (
  select id from orgs where slug = 'default' limit 1
)
update kb_documents
set org_id = (select id from default_org)
where org_id is null;

with default_org as (
  select id from orgs where slug = 'default' limit 1
)
update conversations
set org_id = (select id from default_org)
where org_id is null;

with default_org as (
  select id from orgs where slug = 'default' limit 1
)
update tickets
set org_id = (select id from default_org)
where org_id is null;

with default_org as (
  select id from orgs where slug = 'default' limit 1
)
update agent_runs
set org_id = (select id from default_org)
where org_id is null;

update kb_chunks kc
set org_id = kd.org_id
from kb_documents kd
where kc.document_id = kd.id and kc.org_id is null;

alter table kb_documents
  add constraint kb_documents_org_id_fk
  foreign key (org_id) references orgs(id) on delete cascade;

alter table kb_chunks
  add constraint kb_chunks_org_id_fk
  foreign key (org_id) references orgs(id) on delete cascade;

alter table conversations
  add constraint conversations_org_id_fk
  foreign key (org_id) references orgs(id) on delete cascade;

alter table tickets
  add constraint tickets_org_id_fk
  foreign key (org_id) references orgs(id) on delete cascade;

alter table agent_runs
  add constraint agent_runs_org_id_fk
  foreign key (org_id) references orgs(id) on delete cascade;

alter table kb_documents alter column org_id set not null;
alter table kb_chunks alter column org_id set not null;
alter table conversations alter column org_id set not null;
alter table tickets alter column org_id set not null;
alter table agent_runs alter column org_id set not null;

create index if not exists kb_documents_org_id_idx on kb_documents(org_id);
create index if not exists kb_chunks_org_id_idx on kb_chunks(org_id);
create index if not exists conversations_org_id_idx on conversations(org_id);
create index if not exists tickets_org_id_idx on tickets(org_id);
create index if not exists agent_runs_org_id_idx on agent_runs(org_id);

create or replace function match_kb_chunks(
  query_embedding jsonb,
  match_count int default 5,
  min_similarity float default 0.2,
  p_org_id uuid default null
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
  with query as (
    select array_agg(value::float4) as vec
    from jsonb_array_elements_text(query_embedding) as t(value)
  )
  select
    kc.id,
    kc.document_id,
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
