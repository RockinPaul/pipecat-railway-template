# Deploy and Host Pipecat Voice Agent on Railway

A private AI voice assistant you can talk to in your browser. Deploy one service, add your Daily and OpenAI API keys, and connect with the generated access password.

## About Hosting Pipecat Voice Agent

Pipecat is an open-source framework for voice and multimodal AI. This starter combines its OpenAI Realtime pipeline with Daily's hosted WebRTC transport and a simple browser interface. Railway runs the Python session server and bot; Daily carries the audio and OpenAI generates spoken replies.

The service includes password-protected session creation, private rooms, expiring browser tokens, microphone controls, and automatic bot cleanup. The browser client is bundled into the same container. No database or persistent volume is required.

## Common Use Cases

- A private conversational assistant.
- Prototyping voice agents with a custom system prompt.
- Learning and extending a small Pipecat application on Railway.

## Dependencies and Costs

Supply `DAILY_API_KEY` and `OPENAI_API_KEY`. The OpenAI project must have access to the configured Realtime model and sufficient API credit. Use the generated `ACCESS_PASSWORD` to connect in the browser.

Railway hosting, Daily media usage, and OpenAI API usage are billed separately. This template runs one conversation at a time, with a default ten-minute session limit. It does not include a Pipecat Cloud subscription or autoscaling voice infrastructure.

The app does not record conversations or persist transcripts. Audio is processed by Daily and OpenAI under their policies.

## First Connection

Open the service's Railway HTTPS domain. Enter `ACCESS_PASSWORD` from Variables, click Connect, and allow microphone access. You can interrupt the assistant, mute your microphone, or disconnect at any time.

Customize `BOT_PROMPT`, `BOT_VOICE`, or `OPENAI_REALTIME_MODEL` in Variables. Keep the service at one replica; restarting or deploying can interrupt ongoing conversations.
