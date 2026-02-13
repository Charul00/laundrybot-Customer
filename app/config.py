import os
from dotenv import load_dotenv

load_dotenv()


def get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


TELEGRAM_BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "")
SUPABASE_URL = get_env("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = get_env("SUPABASE_SERVICE_KEY", "")
OPENAI_API_KEY = get_env("OPENAI_API_KEY", "")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""
