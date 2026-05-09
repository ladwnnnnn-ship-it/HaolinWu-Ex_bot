# Deploy on Render

## 1. Create the web service

1. Open Render.
2. New -> Web Service.
3. Connect GitHub repo:
   `ladwnnnnn-ship-it/HaolinWu-Ex_bot`
4. Use these settings:

```text
Runtime: Python
Build Command: pip install -r requirements.txt
Start Command: uvicorn bot.app:app --host 0.0.0.0 --port $PORT
Plan: Free
```

The repo also includes `render.yaml`, so Render may detect these automatically.

## 2. Set environment variables

Required:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=...
PUBLIC_BASE_URL=https://your-render-service.onrender.com
LLM_API_BASE=https://your-openai-compatible-api/v1
LLM_API_KEY=...
LLM_MODEL=...
PERSONA_PATH=exes/demosense/SKILL.md
```

Optional:

```text
REDIS_URL=...
HISTORY_TURNS=12
REQUEST_TIMEOUT=60
```

If you do not set `REDIS_URL`, the service uses in-memory history. On Render Free this history is lost when the service restarts or sleeps.

## 3. Deploy twice

First deploy creates the Render URL.

After you know the URL, set:

```text
PUBLIC_BASE_URL=https://your-render-service.onrender.com
```

Then redeploy. On startup, the service automatically calls Telegram `setWebhook`.

## 4. Test

Open:

```text
https://your-render-service.onrender.com/health
```

Then send `/start` to the Telegram bot.

## Free plan note

Render Free services can sleep when idle. The first Telegram message after sleep may be slow. If webhook replies feel unreliable, open `/health` once to wake the service, or upgrade later.
