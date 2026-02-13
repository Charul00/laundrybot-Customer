"""
LangChain custom retriever: uses Supabase pgvector via match_faq_documents RPC.
Returns LangChain Documents for use in create_retrieval_chain.
"""
from typing import Optional

from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_openai import OpenAIEmbeddings

from app.config import OPENAI_API_KEY
from app.db.supabase_client import get_supabase


class SupabaseFAQRetriever(BaseRetriever):
    """
    Retriever over faq_documents table using Supabase RPC match_faq_documents.
    Embeds the query with OpenAI, then runs vector similarity in Postgres.
    """
    k: int = 3
    embeddings: Optional[OpenAIEmbeddings] = None

    class Config:
        arbitrary_types_allowed = True

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: Optional[CallbackManagerForRetrieverRun] = None,
    ) -> list:
        if not OPENAI_API_KEY:
            return []
        emb = self.embeddings or OpenAIEmbeddings(model="text-embedding-ada-002")
        embedding = emb.embed_query(query)
        embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"
        supabase = get_supabase()
        try:
            r = supabase.rpc(
                "match_faq_documents",
                {"query_embedding": embedding_str, "match_count": self.k},
            ).execute()
            if not r.data:
                return []
            return [
                Document(page_content=row.get("content") or "")
                for row in r.data
                if row.get("content")
            ]
        except Exception:
            return []
