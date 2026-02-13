from supabase import create_client
from app.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

_client = None


def get_supabase():
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in .env")
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client
