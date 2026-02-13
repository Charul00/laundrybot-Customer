# Deploy LaundryOps Telegram Bot on Render (24/7)

Follow these steps to deploy the bot on Render so it runs 24/7.

---

## Quick checklist (24/7 deploy)

1. Push bot code to GitHub (repo or subfolder `telegram-bot/`).
2. Create a **Web Service** on Render; set **Root Directory** to `telegram-bot` if the bot is in a subfolder.
3. Set **Build:** `pip install -r requirements.txt` and **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4. Add env vars: `TELEGRAM_BOT_TOKEN`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `OPENAI_API_KEY`.
5. Deploy; copy the service URL (e.g. `https://laundryops-telegram-bot.onrender.com`).
6. Set Telegram webhook: `https://api.telegram.org/bot<TOKEN>/setWebhook?url=<YOUR_RENDER_URL>/webhook`.
7. For **24/7** (no spin-down): use a **paid** plan on Render; free tier sleeps after ~15 min inactivity.

---

## 1. Push your code to GitHub

Push your project to a GitHub repo. Render will deploy from this repo.

- If the **repo root** is the whole project (e.g. `ai-assessment-amber/` with `telegram-bot/` inside), you will set **Root Directory** in step 2.
- If the **repo root** is already the bot folder (only `telegram-bot` contents), leave Root Directory blank.

---

## 2. Create a Web Service on Render

1. Go to **[render.com](https://render.com)** and sign in (or sign up with GitHub).
2. Click **Dashboard** → **New +** → **Web Service**.
3. **Connect** the GitHub repo that contains the bot.
4. **Root Directory (important):**  
   If the bot code is in a subfolder (e.g. `telegram-bot/`), set **Root Directory** to `telegram-bot`.  
   Otherwise leave it blank. Build and start commands run from this folder.

---

## 3. Configure the service

| Field | Value |
|-------|--------|
| **Name** | `laundryops-telegram-bot` (or any name) |
| **Region** | Choose one (e.g. Oregon) |
| **Runtime** | **Python 3** |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |

- Render sets `PORT`; the app must listen on `0.0.0.0` and `$PORT`. The command above does that.
- If you use a **runtime.txt** with `python-3.9.18`, Render will use that Python version.

---

## 4. Add environment variables

In the same Web Service, go to **Environment** and add:

| Key | Value | Secret? |
|-----|--------|--------|
| `TELEGRAM_BOT_TOKEN` | Your bot token from @BotFather | Yes |
| `SUPABASE_URL` | Supabase project URL (Settings → API) | No |
| `SUPABASE_SERVICE_KEY` | Supabase **service_role** key (Settings → API) | Yes |
| `OPENAI_API_KEY` | Your OpenAI API key | Yes |

Mark secrets as **Secret** so they are masked in the dashboard.

---

## 5. Deploy

1. Click **Create Web Service** (or **Save** if you already created it).
2. Render will run **Build** then **Start**. Wait until the service shows **Live** and a green URL like `https://laundryops-telegram-bot.onrender.com`.

---

## 6. Set the Telegram webhook

Replace `YOUR_BOT_TOKEN` and `YOUR_RENDER_URL`:

```
https://api.telegram.org/botYOUR_BOT_TOKEN/setWebhook?url=YOUR_RENDER_URL/webhook
```

Example (use your real token and URL):

```
https://api.telegram.org/bot8235417352:AAxxx/setWebhook?url=https://laundryops-telegram-bot.onrender.com/webhook
```

Open that URL in a browser. You should get: `{"ok":true,"result":true,...}`.

---

## 7. Test the bot

1. Open Telegram and find your bot.
2. Send `/start` or **Book** and confirm the bot replies.
3. Check **Logs** in the Render dashboard if something fails.

---

## Optional: Render Blueprint (render.yaml)

If your repo has a **render.yaml** in the bot root (e.g. `telegram-bot/render.yaml`), you can use **Blueprint**:

1. **New +** → **Blueprint**.
2. Connect the repo and select the **render.yaml** (or the one in the bot folder).
3. Render will create the Web Service from it. You still must:
   - Set **Root Directory** to `telegram-bot` if your repo root is the parent folder.
   - Add **environment variables** (TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_KEY, OPENAI_API_KEY) in the service **Environment** tab.

---

## 24/7 always-on vs free tier

| | Free tier | Paid (Starter or higher) |
|---|-----------|---------------------------|
| **Uptime** | Spins down after ~15 min no traffic | **Runs 24/7**, no spin-down |
| **Cold start** | First request after idle can take 30–60 s | No cold start |
| **Use for** | Testing, low traffic | **Production, 24/7 bot** |

- **For 24/7 production:** Use a **paid** Web Service (Starter or higher) so the bot stays on and responds immediately.
- **Free tier:** Fine for testing; after 15 min of no messages the service sleeps. When someone sends a message, Render wakes it (Telegram may retry); reply can be delayed by ~1 min once.

---

## Troubleshooting

| Issue | What to do |
|--------|------------|
| Build fails | Check **Root Directory** and that `requirements.txt` is in that folder. Check build logs for missing deps. |
| Start / crash | Check **Start Command** and that it uses `$PORT`. Check **Logs** for Python errors. |
| Bot doesn’t reply | Confirm webhook URL is `https://YOUR_SERVICE.onrender.com/webhook` and set via the `setWebhook` link above. Check Render **Logs** when you send a message. |
| 503 / timeout | Free tier cold start; wait ~1 min and try again, or upgrade plan. |
