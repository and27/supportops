drop function if exists match_kb_chunks(jsonb, integer, double precision, uuid);

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
