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
