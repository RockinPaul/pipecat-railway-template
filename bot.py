"""Daily + OpenAI Realtime pipeline, based on Pipecat's BSD-licensed example.

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
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.services.openai.realtime.events import (
    AudioConfiguration, AudioInput, AudioOutput, InputAudioNoiseReduction,
    SemanticTurnDetection, SessionProperties,
)
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport
from pipecat.workers.runner import WorkerRunner


async def run_bot(room_url: str, token: str):
    transport = DailyTransport(room_url, token, "Voice assistant", DailyParams(
        audio_in_enabled=True, audio_out_enabled=True,
    ))
    llm = OpenAIRealtimeLLMService(
        api_key=os.environ["OPENAI_API_KEY"],
        settings=OpenAIRealtimeLLMService.Settings(
            model=os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1-mini"),
            system_instruction=os.getenv("BOT_PROMPT") or (
                "You are a helpful AI voice assistant. Speak naturally and keep answers brief "
                "unless asked for detail. Be clear that you are an AI. Do not claim to perform "
                "actions or access information you cannot access."
            ),
            session_properties=SessionProperties(audio=AudioConfiguration(
                input=AudioInput(
                    turn_detection=SemanticTurnDetection(),
                    noise_reduction=InputAudioNoiseReduction(type="near_field"),
                ),
                output=AudioOutput(voice=os.getenv("BOT_VOICE", "alloy")),
            )),
        ),
    )
    context = LLMContext([{"role": "developer", "content": "Say a short hello and ask how you can help."}])
    user, assistant = LLMContextAggregatorPair(context)
    worker = PipelineWorker(
        Pipeline([transport.input(), user, llm, transport.output(), assistant]),
        params=PipelineParams(enable_metrics=False, enable_usage_metrics=False),
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
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def disconnected(transport, client):
        await runner.cancel()

    await runner.run()


if __name__ == "__main__":
    # Do not log transcripts, tokens, or provider exception bodies.
    logger.remove()
    if "--check" in sys.argv:
        print("Pipecat bot imports OK")
    else:
        try:
            connection = json.loads(sys.stdin.readline())
            asyncio.run(run_bot(connection["room_url"], connection["token"]))
        except Exception as error:
            print(f"Bot stopped ({type(error).__name__})", file=sys.stderr)
            sys.exit(1)
