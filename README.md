# Pipecat Voice Agent for Railway

A private, browser-based AI voice assistant supporting **OpenAI, Gemini, Grok, OpenRouter, and Ollama**. Enter your access password, allow your microphone, and have a spoken conversation. One Railway service serves the browser client and bot; Daily carries the WebRTC audio. Choose the AI provider through environment variables at deployment time.

## What you need

- A [Daily account and API key](https://dashboard.daily.co/).
- The credentials or Ollama endpoint required by your selected provider, listed below.
- A Railway account. **Railway, Daily, and your selected AI/speech providers bill separately.** This is a starter for personal use and small demos, not a managed multi-tenant voice platform.

## Choose a provider

Set `AI_PROVIDER` to one of these values. Only the selected provider's credentials are required. All modes still require `DAILY_API_KEY` and `ACCESS_PASSWORD`.

| `AI_PROVIDER` | Credentials / endpoint | How voice works |
| --- | --- | --- |
| `openai` (default) | `OPENAI_API_KEY` | OpenAI Realtime handles speech directly. Default: `gpt-realtime-2.1-mini`. |
| `gemini` | `GOOGLE_API_KEY` | Gemini Live handles speech directly. Default: `gemini-2.5-flash-native-audio-preview-12-2025`. |
| `grok` | `XAI_API_KEY` | xAI's Grok Voice Agent handles speech directly. Default: `grok-voice-latest`. |
| `openrouter` | `OPENROUTER_API_KEY` | Speech recognition → routed LLM → speech synthesis. By default, all three use the same OpenRouter key. |
| `ollama` | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, plus a speech-provider key | Your Ollama model handles text. OpenAI speech is the default; choose `SPEECH_PROVIDER=openrouter` to use OpenRouter speech instead. |

For OpenRouter, the default text model is `google/gemini-2.5-flash-lite`, recognition uses `openai/whisper-large-v3-turbo`, and speech uses `hexgrad/kokoro-82m` with voice `af_heart`. These model IDs were checked against the provider catalogue; access, pricing, and availability depend on your account and may change.

`SPEECH_PROVIDER` applies only to OpenRouter and Ollama. Leave it empty to use the defaults above, or set `openai` / `openrouter` explicitly. For example, OpenRouter with `SPEECH_PROVIDER=openai` needs **both** `OPENROUTER_API_KEY` and `OPENAI_API_KEY`. Native OpenAI, Gemini, and Grok modes ignore this setting.

Ollama is a connection option, not an automatically provisioned inference server. Supply a running server with the requested model already installed. Examples: `http://ollama.railway.internal:11434/v1` for another service in the same Railway project, or an HTTPS endpoint you control. `localhost` inside Railway refers to the Pipecat container, not your laptop. An optional `OLLAMA_API_KEY` supports protected endpoints; do not embed credentials in the URL. Model inference requires your own compute, and speech services are still billed separately.

Create provider keys through [OpenAI](https://platform.openai.com/api-keys), [Google AI Studio](https://aistudio.google.com/apikey), [xAI](https://console.x.ai/), or [OpenRouter](https://openrouter.ai/keys). A key for one provider cannot be substituted for another provider's key.

## Deploy on Railway

Connect this repository as a single service. Railway builds the Dockerfile. Configure these variables before deploying:

For marketplace maintainers, `.railway/template-variables.json` contains the exact field defaults, descriptions, and optional flags to copy into the Railway template editor. It is an editor reference, not a CLI import command. Provider keys are optional in the deployment form because they are conditional; the application rejects missing keys for the selected mode before creating any Daily rooms.

| Variable | Required | Default / purpose |
| --- | --- | --- |
| `AI_PROVIDER` | No | `openai`; alternatives: `gemini`, `grok`, `openrouter`, `ollama`. |
| `DAILY_API_KEY` | Yes | Daily server API key; no whitespace. |
| `OPENAI_API_KEY` | Conditional | Required for OpenAI Realtime or OpenAI speech. |
| `GOOGLE_API_KEY` | Conditional | Required for Gemini Live. |
| `XAI_API_KEY` | Conditional | Required for Grok Voice Agent. |
| `OPENROUTER_API_KEY` | Conditional | Required for OpenRouter LLM or speech. |
| `ACCESS_PASSWORD` | Yes | Random password of at least 24 characters. The template should generate it with `${{secret(48)}}`. |
| `OPENAI_REALTIME_MODEL` | No | `gpt-realtime-2.1-mini`. Choose a Realtime model available to your OpenAI project. |
| `BOT_VOICE` | No | `alloy`; used only by OpenAI Realtime / OpenAI speech. |
| `GEMINI_MODEL`, `GEMINI_VOICE` | No | `gemini-2.5-flash-native-audio-preview-12-2025`, `Charon`. |
| `GROK_MODEL`, `GROK_VOICE` | No | `grok-voice-latest`, `eve`. |
| `OPENROUTER_MODEL` | No | `google/gemini-2.5-flash-lite`. |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | For Ollama | Reachable HTTP(S) endpoint and an installed model name. A root URL is normalized to `/v1`. |
| `OLLAMA_API_KEY` | No | Optional authentication for a protected Ollama endpoint. |
| `SPEECH_PROVIDER` | No | Empty = OpenRouter speech for OpenRouter; OpenAI speech for Ollama. |
| `OPENAI_STT_MODEL`, `OPENAI_TTS_MODEL` | No | `gpt-4o-mini-transcribe`, `gpt-4o-mini-tts`. |
| `OPENROUTER_STT_MODEL` | No | `openai/whisper-large-v3-turbo`. |
| `OPENROUTER_TTS_MODEL`, `OPENROUTER_TTS_VOICE` | No | `hexgrad/kokoro-82m`, `af_heart`. |
| `OPENROUTER_TTS_SAMPLE_RATE` | No | `24000`; must match the selected TTS model's returned mono, signed 16-bit little-endian PCM. Change it when using a model with a different native rate. |
| `BOT_PROMPT` | No | A brief, helpful AI voice assistant. |
| `MAX_SESSION_SECONDS` | No | `600`; allowed range 30–1800 seconds. |
| `PORT` | Automatic | Supplied by Railway; local default `8080`. |

Generate a public Railway domain. Open its HTTPS URL, copy `ACCESS_PASSWORD` from the service's Variables tab into the app, and click **Connect**. The app requests microphone access before creating a paid voice session. Camera access is disabled.

Use **one replica and one Uvicorn worker**. The single session slot and startup cooldown are process-local. There is no database, volume, queue, or separate frontend service.

The template service should use Dockerfile auto-detection, `/health` with a 120-second startup timeout, one replica, serverless disabled, an `ON_FAILURE` restart policy with three retries, and 25 seconds of deployment draining. The app listens on Railway's `PORT`.

The checked-in `.railway/railway.ts` declares these settings using Railway's current Infrastructure as Code SDK. After `npm ci` and linking your project, run `railway config plan` to inspect the changes and `railway config apply` to apply them. It declares this GitHub repository as the source and preserves the listed application variables. If you fork/eject the template, change its `github()` source to your own repository before applying. Add any extra variables to its `env` block with `preserve()` before applying: omitted variables can otherwise be deleted. IaC is evaluated by the CLI; a GitHub push alone does not apply it. Do not introduce the deprecated `railway.toml`/`railway.json` format.

In the template service's build settings, set watch paths to `/server.py`, `/bot.py`, `/providers.py`, `/speech.py`, `/client.js`, `/static/**`, `/pyproject.toml`, `/uv.lock`, `/package*.json`, and `/Dockerfile` so documentation-only changes do not rebuild the app.

## Run locally

Requirements: Python 3.12, uv, Node.js 22+, and npm.

1. Run `npm ci` and `npm run build`.
2. Run `uv sync --frozen --no-dev --no-install-project`.
3. Copy `.env.example` to `.env`, choose `AI_PROVIDER`, and fill in only its required keys, Daily key, and a generated password.
4. Run `uv run --env-file .env python server.py`.
5. Open `http://localhost:8080`. Remote browser microphone access requires HTTPS.

To generate a password: `python -c "import secrets; print(secrets.token_urlsafe(36))"`.

The browser SDK is bundled locally. Provider keys remain on the server. The browser receives only a short-lived token for its private Daily room; this is distinct from the app access password and the Daily API key.

## Session lifecycle and limits

One conversation can run at a time. Each conversation gets a private Daily room (two participants maximum) and its own Python bot process. The app waits for the bot to join before returning browser credentials. Room and meeting-token expiry limit the session even if the host is abruptly stopped. Disconnect, bot exit, startup failure, and orderly shutdown trigger process and room cleanup. A 60-second idle limit also ends unattended bots.

New starts have a five-second cooldown. There is no public anonymous access, recording, transcript persistence, or account system. The provider is selected by the deployment owner; browser callers cannot switch it or submit custom provider endpoints. The page identifies the selected services. Conversation data goes to Daily and the configured AI/speech providers; OpenRouter also routes data to the selected upstream providers. Their data-processing and retention policies still apply. Do not put private credentials in `BOT_PROMPT`.

Deployments/restarts can interrupt an active conversation. This starter does not promise uninterrupted calls during upgrades or automatic multi-replica scaling. Add a shared session dispatcher before increasing replica/worker counts.

`/health` checks initialized application readiness without provider calls or charges. It does **not** verify that API credit, provider authentication, or live audio works, and Railway's deployment healthcheck is not continuous monitoring.

## Verification

Run `uv run python -m unittest discover -s tests -v`, `npm test`, `npm run check`, `npm run build`, and `uv run python bot.py --check`. The automated tests use fake provider responses, bot processes, and browser SDK behavior; they never spend API credit and do not establish live audio.

All five native adapters are constructed in offline tests. OpenRouter STT multipart requests and TTS PCM responses are checked with mocked HTTP transport, along with key isolation and conditional configuration validation. The OpenAI reference route has been tested with live synthetic browser audio. Gemini, Grok, OpenRouter, and an actual Ollama server still require their own live credentials/endpoint verification; do not equate adapter tests with provider availability or latency guarantees.

Before publishing the marketplace template, deploy a **fresh copy from the saved template** with real keys. Test authentication, microphone denial, spoken question/answer, interruption, mute/unmute, disconnect, reconnect, expiry, and an invalid provider key. Check the old bot exits and its Daily room is deleted. A green reference deployment alone is insufficient.

To update, pin the new Pipecat release, regenerate `uv.lock`, rebuild, and repeat these checks. Do not use floating upstream `main` for Python dependencies. The pipelines use Pipecat's native [OpenRouter](https://docs.pipecat.ai/api-reference/server/services/llm/openrouter), [Gemini Live](https://docs.pipecat.ai/api-reference/server/services/s2s/gemini-live), [Grok](https://docs.pipecat.ai/api-reference/server/services/s2s/grok), and OpenAI-compatible adapters. The bot is adapted from [Pipecat's Realtime examples at v1.8.1](https://github.com/pipecat-ai/pipecat/tree/v1.8.1/examples/realtime); its public development runner is not exposed. OpenRouter's [multipart STT](https://openrouter.ai/docs/guides/overview/multimodal/stt) and [PCM TTS](https://openrouter.ai/docs/guides/overview/multimodal/tts) endpoints supply the optional speech chain.

## License

BSD-2-Clause. See `LICENSE` and `THIRD_PARTY_NOTICES.md`.
