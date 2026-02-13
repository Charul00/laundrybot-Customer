-- Run this in Supabase SQL Editor if you use RAG. Required for match_faq_documents RPC.

-- Match FAQ documents by embedding similarity (for RAG).
-- query_embedding: pass as text form of vector, e.g. '[0.1, 0.2, ...]'
create or replace function match_faq_documents(
  query_embedding text,
  match_count int default 3
)
returns table (id uuid, content text)
language plpgsql
as $$
begin
  return query
  select faq_documents.id, faq_documents.content
  from faq_documents
  where faq_documents.embedding is not null
  order by faq_documents.embedding <=> query_embedding::vector(1536)
  limit match_count;
end;
$$;
