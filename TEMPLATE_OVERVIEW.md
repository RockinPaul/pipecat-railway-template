# Deploy and Host Pipecat on Railway

Pipecat is an open-source Python framework for building voice and multimodal AI agents. This template packages Pipecat 1.8.1 as a password-protected voice app you can use in your browser, with a choice of OpenAI, Gemini, Grok, OpenRouter, or Ollama. It deploys one Railway service containing the bot, session API, and web client, with Daily handling the WebRTC audio connection.

## About Hosting Pipecat

Hosting this template on Railway means one Docker-based service and no database or persistent volume. Your browser joins a private Daily room using a short-lived token, and a dedicated bot process joins the same room to listen and respond. The browser interface includes microphone controls, connection status, a session timer, and a password prompt; provider API keys stay on the server.

OpenAI, Gemini, and Grok handle speech directly through their realtime voice APIs. OpenRouter and Ollama use a speech-recognition, language-model, and speech-synthesis pipeline. You select the provider, model, voice, and assistant instructions through deployment variables. The template includes an authenticated session server rather than exposing Pipecat's development runner.

## Common Use Cases

- A private voice assistant for asking questions, brainstorming, and thinking through ideas aloud
- Prototyping voice agents with different model providers and a custom system prompt
- Adding a browser voice interface to an existing Ollama model server
- A small, self-hosted starting point for extending Pipecat's conversation pipelines

## Dependencies for Pipecat Hosting

- A Railway account
- A Daily WebRTC API key, supplied as `DAILY_API_KEY` in every mode
- An API key for the selected AI provider, with access to the configured models and sufficient quota or credit
- A browser with microphone access; use the generated HTTPS domain for remote connections
- For Ollama: a reachable model server with the selected model already installed, plus an OpenAI or OpenRouter key for speech

### Deployment Dependencies

- Pipecat upstream repository: https://github.com/pipecat-ai/pipecat
- Pipecat documentation: https://docs.pipecat.ai/
- Daily developer documentation: https://docs.daily.co/
- Template repository and complete variable reference: https://github.com/RockinPaul/pipecat-railway-template
- OpenRouter audio APIs: https://openrouter.ai/docs/guides/overview/multimodal/overview

### Implementation Details

- `pipecat`: a single Docker service running Python 3.12 and pinned Pipecat dependencies, with the browser client bundled into the same container. It listens on `PORT` (default `8080`) and exposes `/health` for deployment readiness.
- Access: `ACCESS_PASSWORD` is generated during deployment. Session creation requires this password; the browser receives only a short-lived token for its private Daily room.
- Sessions: one conversation at a time, with a separate bot process per conversation. Disconnects, inactivity, and session expiry trigger cleanup. `MAX_SESSION_SECONDS` defaults to `600` and accepts values from `30` to `1800`.
- Storage: the app does not persist recordings or transcripts. Daily and the configured AI/speech services process conversation data under their own policies; OpenRouter also routes data to its selected upstream providers.

Set `AI_PROVIDER` to choose the conversation backend:

- `openai`: requires `OPENAI_API_KEY`. Uses OpenAI Realtime, with `gpt-realtime-2.1-mini` as the default model.
- `gemini`: requires `GOOGLE_API_KEY`. Uses Gemini Live with separate `GEMINI_MODEL` and `GEMINI_VOICE` settings.
- `grok`: requires `XAI_API_KEY`. Uses xAI's Grok Voice Agent with `GROK_MODEL` and `GROK_VOICE` settings.
- `openrouter`: requires `OPENROUTER_API_KEY`. By default, the same key covers the text model, transcription, and speech synthesis. The starter uses Gemini Flash-Lite, Whisper Large V3 Turbo, and Kokoro through OpenRouter, with each model configurable.
- `ollama`: requires `OLLAMA_BASE_URL` and `OLLAMA_MODEL`. It connects to an existing server; it does not install Ollama or download models. OpenAI supplies speech by default, or set `SPEECH_PROVIDER=openrouter` to use OpenRouter speech instead.

For OpenRouter and Ollama, `SPEECH_PROVIDER` can explicitly select `openai` or `openrouter`; supply the corresponding speech-provider key. Unused provider keys can remain empty. An Ollama URL must be reachable from Railway: `localhost` refers to the Pipecat container, not your laptop.

First connection: open the service's public domain, copy `ACCESS_PASSWORD` from Railway's Variables tab, click **Connect**, and allow microphone access. You can interrupt the assistant, mute your microphone, or disconnect. Set `BOT_PROMPT` to customize its instructions, and use the provider-specific model and voice variables for further changes.

Keep the service at one replica and one worker. Deployments can interrupt an ongoing conversation, and multiple simultaneous sessions require additional session-management infrastructure. Railway hosting, Daily media, and AI/speech usage are billed separately; this template does not require a Pipecat Cloud subscription.

## Why Deploy Pipecat on Railway?

Railway provides the Docker build, HTTPS domain, environment variables, logs, and deployment healthcheck in one project. The web client and bot deploy together, and hosted AI providers handle model inference without a GPU in the Pipecat service. This keeps the infrastructure small while giving you a working browser voice app and a codebase you can extend. If you choose Ollama, its inference server and compute remain separate from this template.
