# Deploy and Host Pipecat Voice Agent on Railway

A private AI voice assistant with your choice of **OpenAI, Gemini, Grok, OpenRouter, or Ollama**. Deploy one service, supply the keys for your selected provider, and connect in your browser with the generated access password.

## About Hosting Pipecat Voice Agent

Pipecat is an open-source framework for voice and multimodal AI. This starter combines its provider adapters with Daily's hosted WebRTC transport and a simple browser interface. Railway runs the Python session server and bot. Set `AI_PROVIDER` to choose your backend:

- **OpenAI:** direct speech-to-speech with `gpt-realtime-2.1-mini` by default.
- **Gemini:** Google's Gemini Live voice models, using `GOOGLE_API_KEY`.
- **Grok:** xAI's Grok Voice Agent, using `XAI_API_KEY`.
- **OpenRouter:** a routed language model plus speech recognition and synthesis through one `OPENROUTER_API_KEY` by default.
- **Ollama:** connect an existing, reachable Ollama server and installed model; choose OpenAI or OpenRouter for speech.

The service includes password-protected session creation, private rooms, expiring browser tokens, microphone controls, and automatic bot cleanup. The browser client is bundled into the same container. No database or persistent volume is required.

## Common Use Cases

- A private conversational assistant.
- Prototyping voice agents with a custom system prompt.
- Learning and extending a small Pipecat application on Railway.

## Dependencies and Costs

Supply `DAILY_API_KEY` and the credentials required by your selected `AI_PROVIDER`. Unused provider keys can stay empty. Use the generated `ACCESS_PASSWORD` to connect in the browser. Provider accounts must have model access and sufficient quota/credit.

For `AI_PROVIDER=ollama`, set `OLLAMA_BASE_URL` and `OLLAMA_MODEL`. The default speech provider is OpenAI, requiring `OPENAI_API_KEY`; set `SPEECH_PROVIDER=openrouter` to use `OPENROUTER_API_KEY` instead. This template does not install or provision an Ollama model server, and Railway cannot reach your laptop through `localhost`.

Railway hosting, Daily media, and selected model/speech services are billed separately. This template runs one conversation at a time, with a default ten-minute session limit. It does not include a Pipecat Cloud subscription or autoscaling voice infrastructure. Cheaper LLM tokens do not eliminate speech or hosting costs.

The app does not record conversations or persist transcripts. Conversation data is processed by Daily and the configured AI/speech services (including OpenRouter's upstream providers) under their policies.

## First Connection

Open the service's Railway HTTPS domain. Enter `ACCESS_PASSWORD` from Variables, click Connect, and allow microphone access. You can interrupt the assistant, mute your microphone, or disconnect at any time.

Customize `BOT_PROMPT` and your provider's model/voice variables. Provider selection is controlled through deployment variables, not by anonymous browser callers. Keep the service at one replica; restarting or deploying can interrupt ongoing conversations.
