"""Daily voice pipelines using Pipecat's native provider adapters.

Upstream: pipecat-ai/pipecat, examples/realtime/realtime-openai.py (v1.8.1).
Copyright (c) 2024-2026, Daily. See THIRD_PARTY_NOTICES.md.
"""

import asyncio
import json
import os
import sys

from loguru import logger
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair, LLMUserAggregatorParams
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.workers.runner import WorkerRunner

from providers import TEXT_PROVIDERS, ollama_base_url, setting, speech_provider, validate_provider_environment


def bot_prompt() -> str:
    return setting("BOT_PROMPT", (
        "You are a helpful AI voice assistant. Speak naturally and keep answers brief "
        "unless asked for detail. Be clear that you are an AI. Do not claim to perform "
        "actions or access information you cannot access."
    ))


def create_llm(provider: str):
    if provider == "openai":
        from pipecat.services.openai.realtime.events import (
            AudioConfiguration, AudioInput, AudioOutput, InputAudioNoiseReduction,
            SemanticTurnDetection, SessionProperties,
        )
        from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService

        return OpenAIRealtimeLLMService(
            api_key=os.environ["OPENAI_API_KEY"],
            settings=OpenAIRealtimeLLMService.Settings(
                model=setting("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini"),
                system_instruction=bot_prompt(),
                session_properties=SessionProperties(audio=AudioConfiguration(
                    input=AudioInput(
                        turn_detection=SemanticTurnDetection(),
                        noise_reduction=InputAudioNoiseReduction(type="near_field"),
                    ),
                    output=AudioOutput(voice=setting("BOT_VOICE", "alloy")),
                )),
            ),
        )
    if provider == "gemini":
        from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

        return GeminiLiveLLMService(
            api_key=os.environ["GOOGLE_API_KEY"],
            settings=GeminiLiveLLMService.Settings(
                model=setting("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"),
                voice=setting("GEMINI_VOICE", "Charon"),
                system_instruction=bot_prompt(),
            ),
        )
    if provider == "grok":
        from pipecat.services.xai.realtime.events import SessionProperties
        from pipecat.services.xai.realtime.llm import GrokRealtimeLLMService

        return GrokRealtimeLLMService(
            api_key=os.environ["XAI_API_KEY"],
            settings=GrokRealtimeLLMService.Settings(
                model=setting("GROK_MODEL", "grok-voice-latest"),
                system_instruction=bot_prompt(),
                session_properties=SessionProperties(voice=setting("GROK_VOICE", "eve")),
            ),
        )
    if provider == "openrouter":
        from pipecat.services.openrouter.llm import OpenRouterLLMService

        return OpenRouterLLMService(
            api_key=os.environ["OPENROUTER_API_KEY"],
            settings=OpenRouterLLMService.Settings(
                model=setting("OPENROUTER_MODEL", "google/gemini-2.5-flash-lite"),
            ),
        )
    if provider == "ollama":
        from pipecat.services.openai.llm import OpenAILLMService

        # Ollama speaks OpenAI's chat API. Its native adapter hardcodes the
        # dummy key, so use the shared adapter to also support protected hosts.
        return OpenAILLMService(
            api_key=setting("OLLAMA_API_KEY", "ollama"),
            base_url=ollama_base_url(),
            settings=OpenAILLMService.Settings(model=setting("OLLAMA_MODEL")),
        )
    raise ValueError("Unsupported AI provider")


def create_speech_services(provider: str):
    from pipecat.services.openai.stt import OpenAISTTService

    if provider == "openrouter":
        from speech import OpenRouterTTSService

        return (
            OpenAISTTService(
                api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1",
                settings=OpenAISTTService.Settings(
                    model=setting("OPENROUTER_STT_MODEL", "openai/whisper-large-v3-turbo"),
                ),
            ),
            OpenRouterTTSService(
                api_key=os.environ["OPENROUTER_API_KEY"],
                model=setting("OPENROUTER_TTS_MODEL", "hexgrad/kokoro-82m"),
                voice=setting("OPENROUTER_TTS_VOICE", "af_heart"),
                sample_rate=int(setting("OPENROUTER_TTS_SAMPLE_RATE", "24000")),
            ),
        )
    if provider == "openai":
        from pipecat.services.openai.tts import OpenAITTSService

        return (
            OpenAISTTService(
                api_key=os.environ["OPENAI_API_KEY"],
                settings=OpenAISTTService.Settings(model=setting("OPENAI_STT_MODEL", "gpt-4o-mini-transcribe")),
            ),
            OpenAITTSService(
                api_key=os.environ["OPENAI_API_KEY"],
                settings=OpenAITTSService.Settings(
                    model=setting("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
                    voice=setting("BOT_VOICE", "alloy"),
                ),
            ),
        )
    raise ValueError("Unsupported speech provider")


async def run_bot(room_url: str, token: str):
    provider = validate_provider_environment()
    transport = DailyTransport(room_url, token, "Voice assistant", DailyParams(
        audio_in_enabled=True, audio_out_enabled=True,
    ))
    llm = create_llm(provider)
    stt = tts = None
    user_params = None
    messages = []
    if provider in TEXT_PROVIDERS or provider == "gemini":
        from pipecat.audio.vad.silero import SileroVADAnalyzer

        # Gemini needs local speech activity frames for the worker's idle timer.
        user_params = LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer())
    if provider in TEXT_PROVIDERS:
        stt, tts = create_speech_services(speech_provider(provider))
        messages = [{"role": "system", "content": bot_prompt()}]
    context = LLMContext(messages)
    user, assistant = LLMContextAggregatorPair(context, user_params=user_params)
    processors = [transport.input()]
    if stt:
        processors.append(stt)
    processors.extend([user, llm])
    if tts:
        processors.append(tts)
    processors.extend([transport.output(), assistant])
    worker = PipelineWorker(
        Pipeline(processors),
        params=PipelineParams(enable_metrics=False, enable_usage_metrics=False),
        # This browser uses Daily directly; do not broadcast provider errors or
        # transcript metadata through an unused RTVI channel.
        enable_rtvi=False,
        idle_timeout_secs=60,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=True)
    await runner.add_workers(worker)

    @transport.event_handler("on_joined")
    async def joined(transport, data):
        print("PIPECAT_READY", flush=True)

    @transport.event_handler("on_client_connected")
    async def connected(transport, client):
        context.add_message({"role": "user", "content": "Say a short hello and ask how you can help."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def disconnected(transport, client):
        await runner.cancel()

    await runner.run()


if __name__ == "__main__":
    # Do not log transcripts, tokens, or provider exception bodies.
    logger.remove()
    if "--check" in sys.argv:
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
        from pipecat.services.xai.realtime.llm import GrokRealtimeLLMService
        from pipecat.services.openrouter.llm import OpenRouterLLMService
        from pipecat.services.openai.llm import OpenAILLMService
        from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
        from pipecat.services.openai.stt import OpenAISTTService
        from pipecat.services.openai.tts import OpenAITTSService
        from speech import OpenRouterTTSService

        print("All five AI provider adapters and both speech providers import OK")
    else:
        try:
            connection = json.loads(sys.stdin.readline())
            asyncio.run(run_bot(connection["room_url"], connection["token"]))
        except Exception as error:
            print(f"Bot stopped ({type(error).__name__})", file=sys.stderr)
            sys.exit(1)
