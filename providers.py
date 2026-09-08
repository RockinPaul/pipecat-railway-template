"""Deployment-time provider selection; never accepts provider settings from a caller."""

import os
from urllib.parse import urlsplit

PROVIDER_NAMES = {
    "openai": "OpenAI",
    "gemini": "Google Gemini",
    "grok": "xAI Grok",
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
}
PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
    "grok": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
TEXT_PROVIDERS = {"openrouter", "ollama"}


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, "").strip() or default


def required_secret(name: str) -> str:
    value = os.getenv(name, "")
    if not value or any(char.isspace() for char in value):
        raise RuntimeError(f"{name} must be set and contain no whitespace")
    return value


def selected_provider() -> str:
    provider = setting("AI_PROVIDER", "openai").lower()
    if provider not in PROVIDER_NAMES:
        raise RuntimeError("AI_PROVIDER must be openai, gemini, grok, openrouter, or ollama")
    return provider


def speech_provider(provider: str) -> str | None:
    if provider not in TEXT_PROVIDERS:
        return None
    default = "openrouter" if provider == "openrouter" else "openai"
    speech = setting("SPEECH_PROVIDER", default).lower()
    if speech not in {"openai", "openrouter"}:
        raise RuntimeError("SPEECH_PROVIDER must be openai or openrouter")
    return speech


def ollama_base_url() -> str:
    value = setting("OLLAMA_BASE_URL")
    try:
        url = urlsplit(value)
        port = url.port
        valid = (
            url.scheme in {"http", "https"} and url.hostname
            and not url.username and not url.password and not url.query and not url.fragment
            and not any(char.isspace() for char in value)
            and (port is None or 1 <= port <= 65535)
        )
    except ValueError:
        valid = False
    if not valid:
        raise RuntimeError("OLLAMA_BASE_URL must be an HTTP(S) URL without credentials, query, or fragment")
    if url.path not in {"", "/"} and not url.path.rstrip("/").endswith("/v1"):
        raise RuntimeError("OLLAMA_BASE_URL must point to the OpenAI-compatible /v1 endpoint")
    return value.rstrip("/") + ("/v1" if url.path in {"", "/"} else "")


def validate_provider_environment() -> str:
    provider = selected_provider()
    if provider in PROVIDER_KEYS:
        required_secret(PROVIDER_KEYS[provider])
    else:
        ollama_base_url()
        if not setting("OLLAMA_MODEL"):
            raise RuntimeError("OLLAMA_MODEL must name a model already available on your Ollama server")
        if os.getenv("OLLAMA_API_KEY"):
            required_secret("OLLAMA_API_KEY")
    speech = speech_provider(provider)
    if speech:
        required_secret(PROVIDER_KEYS[speech])
        if speech == "openrouter":
            try:
                sample_rate = int(setting("OPENROUTER_TTS_SAMPLE_RATE", "24000"))
            except ValueError:
                raise RuntimeError("OPENROUTER_TTS_SAMPLE_RATE must be an integer") from None
            if sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000}:
                raise RuntimeError("OPENROUTER_TTS_SAMPLE_RATE must be a supported PCM sample rate")
    return provider


def public_provider_config(provider: str) -> dict:
    processors = ["Daily", PROVIDER_NAMES[provider]]
    speech = speech_provider(provider)
    if speech:
        processors.append(PROVIDER_NAMES[speech])
    return {
        "provider": provider,
        "providerName": PROVIDER_NAMES[provider],
        "speechProvider": speech,
        "dataProcessors": list(dict.fromkeys(processors)),
    }
