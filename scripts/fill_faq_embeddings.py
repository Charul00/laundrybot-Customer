"""
One-time script: fill embedding column in faq_documents for RAG.
Run from telegram-bot directory:  python scripts/fill_faq_embeddings.py
Requires .env: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY
"""
import sys
from pathlib import Path

# Add project root so app.* imports work
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from openai import OpenAI
from app.db.supabase_client import get_supabase
from app.config import OPENAI_API_KEY


def main():
    if not OPENAI_API_KEY:
        print("Missing OPENAI_API_KEY in .env")
        return
    client = OpenAI(api_key=OPENAI_API_KEY)
    supabase = get_supabase()

    # Fetch rows that have content and (missing or null) embedding
    r = supabase.table("faq_documents").select("id, content").execute()
    if not r.data:
        print("No rows in faq_documents. Add some content first.")
        return

    updated = 0
    for row in r.data:
        content = (row.get("content") or "").strip()
        if not content:
            continue
        doc_id = row["id"]
        try:
            emb = client.embeddings.create(model="text-embedding-ada-002", input=content)
            vec = emb.data[0].embedding  # list of floats
            supabase.table("faq_documents").update({"embedding": vec}).eq("id", doc_id).execute()
            updated += 1
            print(f"Updated embedding for id={doc_id}")
        except Exception as e:
            print(f"Error for id={doc_id}: {e}")

    print(f"Done. Updated {updated} row(s).")


if __name__ == "__main__":
    main()
