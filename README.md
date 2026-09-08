# Pipecat Voice Agent for Railway

A private, browser-based AI voice assistant. Enter your access password, allow your microphone, and have a spoken conversation. The app runs on one Railway service and uses Daily for WebRTC audio and OpenAI Realtime for speech-to-speech AI.

## What you need

- A [Daily account and API key](https://dashboard.daily.co/).
- An [OpenAI API key](https://platform.openai.com/api-keys) with access to the configured Realtime model and available API credit.
- A Railway account. **Railway, Daily, and OpenAI bill separately.** This is a starter for personal use and small demos, not a managed multi-tenant voice platform.

## Deploy on Railway

Connect this repository as a single service. Railway builds the Dockerfile. Configure these variables before deploying:

| Variable | Required | Default / purpose |
| --- | --- | --- |
| `DAILY_API_KEY` | Yes | Daily server API key; no whitespace. |
| `OPENAI_API_KEY` | Yes | OpenAI API key; no whitespace. |
| `ACCESS_PASSWORD` | Yes | Random password of at least 24 characters. The template should generate it with `${{secret(48)}}`. |
| `OPENAI_REALTIME_MODEL` | No | `gpt-realtime-2.1-mini`. Choose a Realtime model available to your OpenAI project. |
| `BOT_VOICE` | No | `alloy`. Must be supported by the selected model. |
| `BOT_PROMPT` | No | A brief, helpful AI voice assistant. |
| `MAX_SESSION_SECONDS` | No | `600`; allowed range 30–1800 seconds. |
| `PORT` | Automatic | Supplied by Railway; local default `8080`. |

Generate a public Railway domain. Open its HTTPS URL, copy `ACCESS_PASSWORD` from the service's Variables tab into the app, and click **Connect**. The app requests microphone access before creating a paid voice session. Camera access is disabled.

Use **one replica and one Uvicorn worker**. The single session slot and startup cooldown are process-local. There is no database, volume, queue, or separate frontend service.

The template service should use Dockerfile auto-detection, `/health` with a 120-second startup timeout, one replica, serverless disabled, an `ON_FAILURE` restart policy with three retries, and 25 seconds of deployment draining. The app listens on Railway's `PORT`.

The checked-in `.railway/railway.ts` declares these settings using Railway's current Infrastructure as Code SDK. After `npm ci` and linking your project, run `railway config plan` to inspect the changes and `railway config apply` to apply them. It declares this GitHub repository as the source and preserves the listed application variables. If you fork/eject the template, change its `github()` source to your own repository before applying. Add any extra variables to its `env` block with `preserve()` before applying: omitted variables can otherwise be deleted. IaC is evaluated by the CLI; a GitHub push alone does not apply it. Do not introduce the deprecated `railway.toml`/`railway.json` format.

In the template service's build settings, set watch paths to `/server.py`, `/bot.py`, `/client.js`, `/static/**`, `/pyproject.toml`, `/uv.lock`, `/package*.json`, and `/Dockerfile` so documentation-only changes do not rebuild the app.

## Run locally

Requirements: Python 3.12, uv, Node.js 22+, and npm.

1. Run `npm ci` and `npm run build`.
2. Run `uv sync --frozen --no-dev --no-install-project`.
3. Copy `.env.example` to `.env` and fill in real keys and a generated password.
4. Run `uv run --env-file .env python server.py`.
5. Open `http://localhost:8080`. Remote browser microphone access requires HTTPS.

To generate a password: `python -c "import secrets; print(secrets.token_urlsafe(36))"`.

The browser SDK is bundled locally. Provider keys remain on the server. The browser receives only a short-lived token for its private Daily room; this is distinct from the app access password and the Daily API key.

## Session lifecycle and limits

One conversation can run at a time. Each conversation gets a private Daily room (two participants maximum) and its own Python bot process. The app waits for the bot to join before returning browser credentials. Room and meeting-token expiry limit the session even if the host is abruptly stopped. Disconnect, bot exit, startup failure, and orderly shutdown trigger process and room cleanup. A 60-second idle limit also ends unattended bots.

New starts have a five-second cooldown. There is no public anonymous access, recording, transcript persistence, account system, or provider selector. Audio is transmitted to Daily and OpenAI; their data-processing and retention policies still apply. Do not put private credentials in `BOT_PROMPT`.

Deployments/restarts can interrupt an active conversation. This starter does not promise uninterrupted calls during upgrades or automatic multi-replica scaling. Add a shared session dispatcher before increasing replica/worker counts.

`/health` checks initialized application readiness without provider calls or charges. It does **not** verify that API credit, provider authentication, or live audio works, and Railway's deployment healthcheck is not continuous monitoring.

## Verification

Run `uv run python -m unittest discover -s tests -v`, `npm test`, `npm run check`, `npm run build`, and `uv run python bot.py --check`. The automated tests use fake provider responses, bot processes, and browser SDK behavior; they never spend API credit and do not establish live audio.

Before publishing the marketplace template, deploy a **fresh copy from the saved template** with real keys. Test authentication, microphone denial, spoken question/answer, interruption, mute/unmute, disconnect, reconnect, expiry, and an invalid provider key. Check the old bot exits and its Daily room is deleted. A green reference deployment alone is insufficient.

To update, pin the new Pipecat release, regenerate `uv.lock`, rebuild, and repeat these checks. Do not use floating upstream `main` for Python dependencies. The bot pipeline is adapted from [Pipecat's OpenAI Realtime example at v1.8.1](https://github.com/pipecat-ai/pipecat/blob/v1.8.1/examples/realtime/realtime-openai.py); its public development runner is deliberately not exposed.

## License

BSD-2-Clause. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
