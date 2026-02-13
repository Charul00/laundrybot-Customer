# LaundryOps Telegram Bot

Customer-facing Telegram bot: **Book** pickup, **Track** order, **Pricing/Support** (RAG), and **natural-language** order queries (e.g. "kitna time lagega?", "my booking details").

## Stack

- **FastAPI** – webhook for Telegram
- **LangChain** – RAG chain (custom retriever + prompt + LLM), NL reply chain
- **Supabase** – Postgres + pgvector (`faq_documents`) for RAG
- **OpenAI** – embeddings (text-embedding-ada-002) + chat (gpt-4o-mini)

## Setup

### 1. Telegram Bot

1. Open Telegram → search **@BotFather**
2. Send `/newbot` → name: e.g. **LaundryOps Pune Bot**
3. Copy the **Bot Token**

### 2. Environment

```bash
cp .env.example .env
```

Edit `.env`:

- `TELEGRAM_BOT_TOKEN` – from BotFather
- `SUPABASE_URL` – Supabase project URL (Settings → API)
- `SUPABASE_SERVICE_KEY` – Supabase **service_role** key (Settings → API)
- `OPENAI_API_KEY` – OpenAI API key

### 3. Database (Supabase)

**Full checklist:** see **[docs/SUPABASE_SETUP.md](docs/SUPABASE_SETUP.md)**. Summary:

1. **SQL Editor** – Run the two migrations in `supabase_migrations/` (add `telegram_chat_id`, create `match_faq_documents` RPC).
2. **FAQ embeddings** – Run once: `python scripts/fill_faq_embeddings.py` (so RAG pricing/FAQ answers work).
3. **(Optional) Dummy data** – Run once: `python scripts/seed_dummy_data.py` (customers, orders, feedback for testing Track / "Where is my order?").

### 4. Install and run

```bash
cd telegram-bot
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

- Local: `http://localhost:8000`
- **Auto-reload:** Code changes restart the server automatically. With ngrok, you don't need to restart ngrok — only the server restarts.
- **Expose and test on Telegram:** full steps (ngrok, set webhook, example queries) → **[docs/EXPOSE_AND_TEST_BOT.md](docs/EXPOSE_AND_TEST_BOT.md)**.
- **Deploy 24/7 on Render:** build, env vars, webhook → **[docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)**.

### 5. Set Telegram webhook

Replace `YOUR_TOKEN` and `YOUR_HTTPS_URL`:

```
https://api.telegram.org/botYOUR_TOKEN/setWebhook?url=YOUR_HTTPS_URL/webhook
```

Example:

```
https://api.telegram.org/bot123:ABC/setWebhook?url=https://abc123.ngrok.io/webhook
```

## Flows

| User says | Behavior |
|-----------|----------|
| `/start` | Welcome menu (Book, Track, Pricing, Support) |
| Book / pickup | Asks address → phone → creates customer + order, returns Order ID |
| Track / ORD-xxxx | Returns status, delivery time, outlet |
| Pricing / support / complaint | RAG over `faq_documents` + LLM answer |
| "Where is my order?", "Kitna time lagega?" | NL → resolve customer/order from DB → LLM reply |

## Project layout

- `main.py` – FastAPI app, `/webhook`, `send_message`
- `app/config.py` – env vars
- `app/db/supabase_client.py` – Supabase client
- `app/retrievers/supabase_faq_retriever.py` – **LangChain** custom retriever (Supabase pgvector via `match_faq_documents` RPC)
- `app/services/chatbot_service.py` – intent router + booking state
- `app/services/booking_service.py` – create customer + order, assign outlet
- `app/services/tracking_service.py` – get order by number or by `telegram_chat_id`
- `app/services/rag_service.py` – **LangChain** RAG chain (retriever → format context → prompt → ChatOpenAI → StrOutputParser)
- `app/services/nl_query_service.py` – **LangChain** chain for order NL queries (order data + user message → ChatOpenAI → reply)
- `supabase_migrations/` – SQL to run in Supabase (telegram_chat_id, vector RPC)
- `scripts/fill_faq_embeddings.py` – one-time: fill `faq_documents.embedding` for RAG
- `scripts/seed_dummy_data.py` – optional: insert dummy customers, orders, feedback
- `docs/EXPOSE_AND_TEST_BOT.md` – ngrok + webhook + example queries to test in Telegram
- `docs/SUPABASE_SETUP.md` – Supabase checklist (migrations, RPC, embeddings, dummy data)
- `docs/DEPLOY_RENDER.md` – Deploy bot on Render (24/7)
- `render.yaml` – Render Blueprint (optional)
- `runtime.txt` – Python version for Render

## Next

- **Admin dashboard** (Next.js/React): analytics, outlets, orders, SLA, feedback (separate repo or same monorepo).
