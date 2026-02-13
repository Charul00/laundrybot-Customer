# Expose your bot and test on Telegram

Follow these steps to make Telegram reach your local server and test real queries.

---

## Step 1: Start your bot (Terminal 1)

```bash
cd "/Users/charulchim/Documents/ai assessment amber /telegram-bot"
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Leave this running. You should see: `Uvicorn running on http://0.0.0.0:8000`.

**Auto-reload:** With `--reload`, when you save a change to any Python file, the server restarts automatically. You do **not** need to restart ngrok — it keeps forwarding to the same port.

---

## Step 2: Install ngrok (one-time)

- **Option A – Homebrew (Mac):**
  ```bash
  brew install ngrok
  ```
- **Option B – Download:** https://ngrok.com/download  
  Unzip and put `ngrok` in your PATH.

- **Sign up (free):** https://ngrok.com → sign up → copy your auth token, then:
  ```bash
  ngrok config add-authtoken YOUR_TOKEN
  ```

---

## Step 3: Expose port 8000 (Terminal 2)

Open a **second terminal**. Run:

```bash
ngrok http 8000
```

You’ll see something like:

```
Forwarding   https://a1b2c3d4.ngrok-free.app -> http://localhost:8000
```

**Copy the HTTPS URL** (e.g. `https://a1b2c3d4.ngrok-free.app`).  
Keep this terminal open; if you close it, the URL stops working.

---

## Step 4: Set Telegram webhook

Replace:

- `YOUR_BOT_TOKEN` → your token from @BotFather  
- `YOUR_NGROK_HTTPS_URL` → the URL from Step 3 (no trailing slash)

Open this in your browser (or use `curl`):

```
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_NGROK_HTTPS_URL/webhook
```

**Example:**
```
https://api.telegram.org/bot7123456789:AAHxY.../setWebhook?url=https://a1b2c3d4.ngrok-free.app/webhook
```

You should get: `{"ok":true,"result":true,...}`.

---

## Step 5: Test in Telegram

1. Open Telegram and find your bot (search by the bot username from BotFather).
2. Send **Start** or tap **Start**.
3. Try the queries below.

---

## Queries to try

| What to send | What should happen |
|--------------|--------------------|
| `/start` or `start` | Welcome menu with Book, Track, Pricing, Support. |
| `Book` or `I want to book pickup` | Bot asks for pickup address. |
| (after address) Send an address, e.g. `123 MG Road, Pune` | Bot asks for phone number. |
| (after phone) Send e.g. `9876543210` | Bot creates order and replies with Order ID (e.g. ORD-XXXXXXXX). |
| `Track` or `track ORD-XXXXXXXX` (use the ID you got) | Bot shows status, delivery time, outlet. |
| `Where is my order?` or `kitna time lagega?` | If you have an order linked to this chat, bot answers in natural language. |
| `Pricing` or `What is the cost of dry clean?` | RAG answer from your FAQ/policies (needs Supabase RAG setup). |
| `Do you offer same day delivery?` | RAG answer (from faq_documents). |
| `Rewash free?` or `complaint` | RAG answer from policies. |

**Suggested order:**  
`/start` → `Book` → give address → give phone → note the **Order ID** → send `Track` or `track ORD-XXXXXXXX` → try `Pricing` or `Where is my order?`.

---

## If the bot doesn’t reply

1. **Terminal 1:** Server still running? No errors when you send a message?
2. **Terminal 2:** ngrok still running? Same HTTPS URL?
3. **Webhook:** Open  
   `https://api.telegram.org/botYOUR_BOT_TOKEN/getWebhookInfo`  
   and check that `url` is your ngrok HTTPS URL + `/webhook`.
4. **Supabase:** If Book or Track fails, check Supabase (tables, migrations, dummy data). See `docs/SUPABASE_SETUP.md`.

---

## If code changes don't show up (bot not updating)

- Start the server **with `--reload`** (Step 1). When you save a file, the server restarts and your changes apply. You do **not** need to restart ngrok.
- If you started without `--reload`, stop (Ctrl+C) and run again: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`

## Stop and use bot again later

- **Stop server:** In Terminal 1 press `Ctrl+C`.
- **Stop ngrok:** In Terminal 2 press `Ctrl+C`.
- **Next time:** ngrok free gives a **new URL** each run. Run ngrok again, then run the **setWebhook** URL again with the new ngrok URL.
