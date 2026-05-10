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
REDIS_URL=...
PERSONA_PATH=exes/demosense/SKILL.md
MESSAGE_IDLE_SECONDS=10
```

If you do not want to commit `exes/demosense`, set `PERSONA_TEXT` to the full `SKILL.md` content in Railway instead.

## Telegram commands

- `/start`: quick hello.
- `/reset`: clear this Telegram chat's Redis history.
- `/whoami`: show persona name.

Normal chat messages are buffered per Telegram chat. The bot waits for
`MESSAGE_IDLE_SECONDS` seconds of silence, then sends the combined message block to
the LLM so short consecutive messages are answered together.

## Important deployment note

The repo `.gitignore` ignores `exes/` for privacy. Railway will not receive `exes/demosense/SKILL.md` unless you either:

1. commit that folder deliberately with `git add -f exes/demosense`, or
2. set `PERSONA_TEXT` in Railway, or
3. change `PERSONA_PATH` to another committed persona file.

Option 2 is more private. Option 1 is easier.
