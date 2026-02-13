import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from dotenv import load_dotenv

from app.services.chatbot_service import handle_message
from app.config import TELEGRAM_BOT_TOKEN

load_dotenv()

TELEGRAM_API = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN', '')}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # cleanup if needed


app = FastAPI(title="LaundryOps Telegram Bot", lifespan=lifespan)


@app.get("/")
async def root():
    return {"status": "ok", "service": "LaundryOps Telegram Bot"}


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"status": "ok"}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text") or ""

    if not text.strip():
        await send_message(chat_id, "Please send a text message.")
        return {"status": "ok"}

    reply = handle_message(str(chat_id), text.strip())
    await send_message(chat_id, reply)

    return {"status": "ok"}


async def send_message(chat_id, text: str):
    if not TELEGRAM_BOT_TOKEN:
        print(f"[DEV] Would send to {chat_id}: {text[:80]}...")
        return
    import httpx
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=10.0,
        )
