import { defineRailway, github, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const pipecat = service("pipecat", {
    source: github("RockinPaul/pipecat-railway-template", { branch: "main" }),
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: 1,
    build: {
      watchPatterns: [
        "/server.py", "/bot.py", "/providers.py", "/speech.py", "/client.js", "/static/**",
        "/pyproject.toml", "/uv.lock", "/package*.json", "/Dockerfile",
      ],
    },
    deploy: {
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 3,
      drainingSeconds: 25,
      sleepApplication: false,
    },
    env: {
      AI_PROVIDER: preserve(),
      DAILY_API_KEY: preserve(),
      OPENAI_API_KEY: preserve(),
      GOOGLE_API_KEY: preserve(),
      XAI_API_KEY: preserve(),
      OPENROUTER_API_KEY: preserve(),
      ACCESS_PASSWORD: preserve(),
      OPENAI_REALTIME_MODEL: preserve(),
      BOT_VOICE: preserve(),
      BOT_PROMPT: preserve(),
      GEMINI_MODEL: preserve(),
      GEMINI_VOICE: preserve(),
      GROK_MODEL: preserve(),
      GROK_VOICE: preserve(),
      OPENROUTER_MODEL: preserve(),
      OLLAMA_BASE_URL: preserve(),
      OLLAMA_MODEL: preserve(),
      OLLAMA_API_KEY: preserve(),
      SPEECH_PROVIDER: preserve(),
      OPENAI_STT_MODEL: preserve(),
      OPENAI_TTS_MODEL: preserve(),
      OPENROUTER_STT_MODEL: preserve(),
      OPENROUTER_TTS_MODEL: preserve(),
      OPENROUTER_TTS_VOICE: preserve(),
      OPENROUTER_TTS_SAMPLE_RATE: preserve(),
      MAX_SESSION_SECONDS: preserve(),
      PORT: preserve(),
    },
  });
  return project("pipecat-railway-template", { resources: [pipecat] });
});
