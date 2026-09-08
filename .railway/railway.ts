import { defineRailway, github, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const pipecat = service("pipecat", {
    source: github("RockinPaul/pipecat-railway-template", { branch: "main" }),
    healthcheck: "/health",
    healthcheckTimeout: 120,
    replicas: 1,
    build: {
      watchPatterns: [
        "/server.py", "/bot.py", "/client.js", "/static/**",
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
      DAILY_API_KEY: preserve(),
      OPENAI_API_KEY: preserve(),
      ACCESS_PASSWORD: preserve(),
      OPENAI_REALTIME_MODEL: preserve(),
      BOT_VOICE: preserve(),
      BOT_PROMPT: preserve(),
      MAX_SESSION_SECONDS: preserve(),
      PORT: preserve(),
    },
  });
  return project("pipecat-railway-template", { resources: [pipecat] });
});
