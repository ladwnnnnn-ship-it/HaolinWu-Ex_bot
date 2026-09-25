# Telegram Bot on Railway

## What this adds

This service exposes a Telegram webhook and talks to an OpenAI-compatible LLM API using the `demosense` persona.

Runtime files:

- `bot/app.py`: FastAPI webhook service.
- `Procfile` / `railway.toml`: Railway start config.
- `.env.example`: required environment variables.

## Railway variables

Set these in Railway:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_WEBHOOK_SECRET=use-a-long-random-string
PUBLIC_BASE_URL=https://your-service.up.railway.app
LLM_API_BASE=https://api.openai.com/v1
LLM_API_KEY=...
LLM_MODEL=gpt-4o-mini
VISION_API_BASE=https://api.deepseek.com/v1
VISION_API_KEY=...
VISION_MODEL=deepseek-flash
VISION_TIMEOUT=45
VISION_MAX_IMAGE_BYTES=8388608
REDIS_URL=...
PERSONA_PATH=exes/demosense/SKILL.md
MESSAGE_IDLE_SECONDS=3
MESSAGE_UNFINISHED_BONUS_SECONDS=12
MESSAGE_QUESTION_DISCOUNT_SECONDS=1.5
MESSAGE_MIN_IDLE_SECONDS=1
MESSAGE_MAX_IDLE_SECONDS=18
MESSAGE_COMPLETION_MODEL_ENABLED=false
MESSAGE_COMPLETION_MODEL_TIMEOUT=1.5
PROACTIVE_TIMEZONE=Asia/Shanghai
PROACTIVE_CHAT_ID=your-telegram-chat-id
PROACTIVE_MIN_IDLE_HOURS=6
PROACTIVE_GAP_HOURS=4
PROACTIVE_PERSONA_SENDER=demosense
```

If you do not want to commit `exes/demosense`, set `PERSONA_TEXT` to the full `SKILL.md` content in Railway instead.

## Telegram commands

- `/start`: quick hello.
- `/reset`: clear this Telegram chat's Redis history.
- `/whoami`: show persona name.
- `/chatid`: show the numeric Telegram chat id to put in `PROACTIVE_CHAT_ID`.

Normal chat messages are buffered per Telegram chat. The bot first estimates a wait
time from fast local rules. Optional LLM-based completion checks can be enabled
with `MESSAGE_COMPLETION_MODEL_ENABLED=true`, but the default is `false` to avoid
extra model calls and provider-side failed/cancelled request logs.

Photo messages use the same buffer, so a caption or a short follow-up such as
`看出来了吗` is analyzed in one turn. The bot downloads only the largest Telegram
photo and processes one photo per turn. The vision model returns grounded JSON;
the persona language model produces the user-facing reply. Image bytes and base64
data are never written to Redis or conversation history.

For DeepSeek, use `VISION_MODEL=deepseek-flash`. If the vision and language calls
share one DeepSeek account, the vision key and base URL inherit `LLM_API_KEY` and
`LLM_API_BASE`; keeping the model variable explicit is still recommended.

Useful tuning variables:

- `MESSAGE_IDLE_SECONDS`: base wait for an ordinary complete-looking message. Keep
  this low for a near-instant reply feel.
- `MESSAGE_UNFINISHED_BONUS_SECONDS`: extra wait when the last message looks like
  it ends mid-thought, such as "就是", "但是", "因为", or a comma.
- `MESSAGE_QUESTION_DISCOUNT_SECONDS`: shorter wait for clear questions.
- `MESSAGE_MIN_IDLE_SECONDS` / `MESSAGE_MAX_IDLE_SECONDS`: lower and upper bounds.
- `MESSAGE_COMPLETION_MODEL_ENABLED`: set to `true` only if you want an extra LLM
  call to judge whether the user has finished the thought.
- `MESSAGE_COMPLETION_MODEL_TIMEOUT`: maximum seconds to wait for the LLM
  completion decision.

## Proactive messages

The bot can occasionally start a chat using the original QQ transcript's initiation
patterns. It extracts moments where `PROACTIVE_PERSONA_SENDER` started a new message
cluster after `PROACTIVE_GAP_HOURS` hours of silence, then uses those time patterns
plus the committed/persona-provided `SKILL.md` as the source of truth.

Trigger it with a scheduler request:

```text
POST https://your-service.up.railway.app/proactive/tick/{TELEGRAM_WEBHOOK_SECRET}
```

Recommended Railway Cron cadence: every 30-60 minutes. The endpoint is conservative:
it only scans the single `PROACTIVE_CHAT_ID`, skips if that chat has not talked to
the bot before, skips users active within `PROACTIVE_MIN_IDLE_HOURS`, and sends at
most one proactive message per day.

`PROACTIVE_CHAT_ID` is required for proactive messages. If it is empty, the endpoint
returns without sending anything. This keeps proactive messaging user-specific even
if other people have chatted with the bot.

The generation prompt is Skill-grounded: timing only decides whether the moment is
plausible; the actual message must follow the demosense Relationship Memory and
Persona instead of generic reminder-bot or ex-bot behavior.

## Important deployment note

The repo `.gitignore` ignores `exes/` for privacy. Railway will not receive `exes/demosense/SKILL.md` unless you either:

1. commit that folder deliberately with `git add -f exes/demosense`, or
2. set `PERSONA_TEXT` in Railway, or
3. change `PERSONA_PATH` to another committed persona file.

Option 2 is more private. Option 1 is easier.
