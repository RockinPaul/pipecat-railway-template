"""OpenRouter PCM speech synthesis, including non-OpenAI voice identifiers."""

import httpx

from pipecat.frames.frames import TTSAudioRawFrame
from pipecat.services.settings import TTSSettings
from pipecat.services.tts_service import TTSService


class OpenRouterTTSService(TTSService):
    def __init__(self, *, api_key: str, model: str, voice: str, sample_rate: int = 24000):
        # ponytail: PCM has no rate metadata; configure the native rate, or add
        # container decoding later if arbitrary routed models need auto-detection.
        # OpenAITTSService validates against OpenAI's voice list, so it cannot
        # serve Kokoro's af_heart or other routed providers' voice identifiers.
        super().__init__(
            sample_rate=sample_rate, push_start_frame=True, push_stop_frames=True,
            settings=TTSSettings(model=model, voice=voice, language=None),
        )
        self._http = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1/",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30,
        )

    async def run_tts(self, text: str, context_id: str):
        try:
            async with self._http.stream("POST", "audio/speech", json={
                "model": self._settings.model,
                "input": text,
                "voice": self._settings.voice,
                "response_format": "pcm",
            }) as response:
                response.raise_for_status()
                if response.headers.get("content-type", "").split(";")[0] not in {
                    "audio/pcm", "application/octet-stream",
                }:
                    raise ValueError("Expected raw PCM speech")
                # iter_bytes assembles even-sized chunks; preserve a final odd
                # byte across network boundaries rather than corrupt PCM samples.
                pending = b""
                async for chunk in response.aiter_bytes(self.chunk_size):
                    pending += chunk
                    size = len(pending) - len(pending) % 2
                    if size:
                        yield TTSAudioRawFrame(pending[:size], self.sample_rate, 1, context_id=context_id)
                        pending = pending[size:]
                if pending:
                    raise ValueError("Incomplete PCM sample")
        except Exception:
            # Do not expose a provider error body or token through logs/frames.
            await self.push_error("OpenRouter speech generation failed", force_treat_as_permanent=True)

    async def cleanup(self):
        try:
            await super().cleanup()
        finally:
            await self._http.aclose()
