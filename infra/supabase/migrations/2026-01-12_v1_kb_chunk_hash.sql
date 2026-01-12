alter table kb_chunks
  add column if not exists chunk_hash text,
  add column if not exists embedding_version text;

create unique index if not exists kb_chunks_document_hash_idx on kb_chunks(document_id, chunk_hash) where chunk_hash is not null;
