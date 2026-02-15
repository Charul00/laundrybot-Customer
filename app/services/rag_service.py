"""
RAG with LangChain: custom Supabase retriever + retrieval chain.
Retrieves from faq_documents (pgvector), then LLM answers pricing, policies, FAQs.
"""
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import OPENAI_API_KEY
from app.retrievers.supabase_faq_retriever import SupabaseFAQRetriever


def _format_docs(docs: list) -> str:
    return "\n\n".join(d.page_content for d in docs if d.page_content)


def _get_fallback_context() -> str:
    """When RAG returns no docs, get services (pricing) + FAQ content from Supabase."""
    try:
        from app.db.supabase_client import get_supabase
        supabase = get_supabase()
        parts = []
        r = supabase.table("services").select("service_name, base_price").execute()
        if r.data:
            def _p(v):
                x = float(v or 0)
                return int(x) if x == int(x) else x
            by_name = {row.get("service_name", ""): _p(row.get("base_price")) for row in r.data}
            wash = by_name.get("wash", 0)
            iron = by_name.get("iron", 0)
            dry_clean = by_name.get("dry_clean", 0)
            shoe_clean = by_name.get("shoe_clean", 0)
            wash_iron_total = wash + iron
            pricing_lines = [
                "Pricing (per kg):",
                f"- Wash only: Rs {wash}/kg",
                f"- Wash + Iron: Rs {wash_iron_total}/kg (wash Rs {wash} + iron Rs {iron})",
                f"- Dry clean: Rs {dry_clean}/kg",
                f"- Shoe clean: Rs {shoe_clean}/kg",
                "Total = weight (kg) × rate. Express delivery: +30% on total. Standard delivery about 48 hours.",
            ]
            parts.append("\n".join(pricing_lines))
        faq = supabase.table("faq_documents").select("content").limit(10).execute()
        if faq.data:
            contents = [row.get("content", "").strip() for row in faq.data if row.get("content")]
            if contents:
                parts.append("Policies / FAQs:\n" + "\n".join(contents))
        return "\n\n".join(parts).strip() if parts else ""
    except Exception:
        return ""


def _answer_with_fallback_context(
    context: str, user_message: str, conversation_history: str = ""
) -> str:
    """Use fallback context with LLM when RAG retriever returned empty."""
    if not OPENAI_API_KEY or not context.strip():
        return (
            "We offer Wash, Dry Clean, Iron, and Shoe cleaning. "
            "For exact prices and support, please visit our outlet."
        )
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", max_tokens=150, api_key=OPENAI_API_KEY)
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "You are a LaundryOps assistant. Answer only from the context. "
                "When the user asks for pricing (wash only, wash+iron, dry clean, shoe clean), include the exact Rs amounts from the context. "
                "If there is recent conversation, use it to understand follow-up questions (e.g. 'and express?', 'same for dry clean?'). "
                "Keep reply clear and short (2-5 lines for pricing questions).",
            ),
            (
                "human",
                "Context:\n{context}\n\n"
                "Recent conversation (for follow-up context):\n{conversation_history}\n\n"
                "Current question: {input}",
            ),
        ])
        chain = prompt | llm | StrOutputParser()
        out = chain.invoke({
            "context": context,
            "input": user_message,
            "conversation_history": conversation_history.strip() or "(none)",
        })
        return (out or "").strip()
    except Exception:
        return (
            "We offer Wash, Dry Clean, Iron, and Shoe cleaning. "
            "For pricing and support, please visit our outlet."
        )


def _get_rag_chain():
    """Build LangChain RAG chain: retriever -> format context -> prompt -> LLM -> string."""
    embeddings = OpenAIEmbeddings(model="text-embedding-ada-002")
    retriever = SupabaseFAQRetriever(k=3, embeddings=embeddings)
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a helpful LaundryOps assistant. Answer only from the given context. "
            "Keep replies short (1-3 sentences). If the context doesn't have the answer, "
            "say you don't have that info and suggest they ask at the outlet.",
        ),
        ("human", "Context:\n{context}\n\nCustomer question: {input}"),
    ])
    llm = ChatOpenAI(model="gpt-4o-mini", max_tokens=150, api_key=OPENAI_API_KEY)

    # LCEL: assign context from retriever, then format -> prompt -> llm -> parse
    chain = (
        RunnablePassthrough.assign(
            context=lambda x: retriever.invoke(x["input"]),
        )
        | (lambda x: {"context": _format_docs(x["context"]), "input": x["input"]})
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain


def _get_pricing_reply() -> str:
    """Return full pricing block (wash only, wash+iron, dry clean, shoe clean) for 'Pricing' / 'price'."""
    fallback = _get_fallback_context()
    if not fallback:
        return (
            "We offer Wash only, Wash + Iron, Dry clean, and Shoe clean. "
            "Express +30%. Visit outlet for exact prices."
        )
    pricing_part = fallback.split("Policies")[0].split("FAQs")[0].strip()
    if "Express" not in pricing_part:
        pricing_part += "\n\nExpress delivery: +30% on total."
    return pricing_part


def answer_with_rag(user_message: str, conversation_history: str = "") -> str:
    """
    LangChain RAG: retrieve relevant FAQ/policy chunks, then generate answer with LLM.
    If retriever returns no context, use fallback (services + faq content from DB).
    When user asks just 'Pricing' or 'price', return full pricing list directly.
    conversation_history: recent "User: ...\\nAssistant: ..." for follow-up context.
    """
    msg_lower = (user_message or "").strip().lower()
    if msg_lower in ("pricing", "price", "prices", "rate", "rates") or msg_lower in ("all prices", "all services price", "what are the prices"):
        return _get_pricing_reply()
    if not OPENAI_API_KEY:
        fallback = _get_fallback_context()
        if fallback and ("price" in msg_lower or "cost" in msg_lower or "pricing" in msg_lower):
            return _get_pricing_reply()
        return (
            "Pricing: We offer Wash, Dry Clean, Iron, and Shoe cleaning. "
            "Express delivery has an additional fee. For exact prices, visit our outlet or ask for a quote."
        )
    try:
        retriever = SupabaseFAQRetriever(k=3, embeddings=OpenAIEmbeddings(model="text-embedding-ada-002"))
        docs = retriever.invoke(user_message)
        context = _format_docs(docs)
        if not context.strip():
            context = _get_fallback_context()
        if not context.strip():
            return (
                "We offer Wash, Dry Clean, Iron, and Shoe cleaning. "
                "Express has an extra fee. For pricing and support, please visit our outlet or ask for a quote."
            )
        return _answer_with_fallback_context(context, user_message, conversation_history)
    except Exception:
        fallback = _get_fallback_context()
        if fallback:
            return _answer_with_fallback_context(fallback, user_message, conversation_history)
        return (
            "We offer Wash, Dry Clean, Iron, and Shoe cleaning. Express has an extra fee. "
            "For pricing and support, please visit our outlet or try again later."
        )
