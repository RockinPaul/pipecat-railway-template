"""Provider configuration and actual SDK wire contracts, without paid API calls."""

import io
import json
import os
import unittest
import wave
from unittest.mock import AsyncMock, patch

import httpx
from openai import AsyncOpenAI

from providers import (
    ollama_base_url, public_provider_config, selected_provider, speech_provider,
    validate_provider_environment,
)


class ProviderConfigurationTests(unittest.TestCase):
    def test_only_selected_provider_keys_are_required(self):
        cases = [
            ({"AI_PROVIDER": "openai", "OPENAI_API_KEY": "test-openai"}, "openai"),
            ({"AI_PROVIDER": "gemini", "GOOGLE_API_KEY": "test-google"}, "gemini"),
            ({"AI_PROVIDER": "grok", "XAI_API_KEY": "test-xai"}, "grok"),
            ({"AI_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test-router"}, "openrouter"),
            ({"AI_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://ollama.railway.internal:11434",
              "OLLAMA_MODEL": "my-model", "OPENAI_API_KEY": "test-openai"}, "ollama"),
        ]
        for env, expected in cases:
            with self.subTest(provider=expected), patch.dict(os.environ, env, clear=True):
                self.assertEqual(validate_provider_environment(), expected)

    def test_missing_selected_key_fails_and_unrelated_key_does_not_help(self):
        for provider, key in [("gemini", "GOOGLE_API_KEY"), ("grok", "XAI_API_KEY"),
                              ("openrouter", "OPENROUTER_API_KEY")]:
            with self.subTest(provider=provider), patch.dict(os.environ, {
                "AI_PROVIDER": provider, "OPENAI_API_KEY": "unrelated-test-key",
            }, clear=True):
                with self.assertRaisesRegex(RuntimeError, key):
                    validate_provider_environment()

    def test_unused_invalid_secret_does_not_block_gemini(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "gemini", "GOOGLE_API_KEY": "test-google",
            "OPENAI_API_KEY": " unused invalid key ", "SPEECH_PROVIDER": "not-used",
        }, clear=True):
            self.assertEqual(validate_provider_environment(), "gemini")

    def test_text_providers_can_choose_either_speech_provider(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://127.0.0.1:11434/v1",
            "OLLAMA_MODEL": "my-model", "SPEECH_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-router",
        }, clear=True):
            self.assertEqual(validate_provider_environment(), "ollama")
            self.assertEqual(public_provider_config("ollama")["dataProcessors"], ["Daily", "Ollama", "OpenRouter"])
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openrouter", "SPEECH_PROVIDER": "openai", "OPENROUTER_API_KEY": "test-router",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                validate_provider_environment()

    def test_defaults_and_invalid_choices(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(selected_provider(), "openai")
            self.assertEqual(speech_provider("openrouter"), "openrouter")
            self.assertEqual(speech_provider("ollama"), "openai")
        with patch.dict(os.environ, {"AI_PROVIDER": "unknown"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AI_PROVIDER"):
                selected_provider()
        with patch.dict(os.environ, {"SPEECH_PROVIDER": "unknown"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SPEECH_PROVIDER"):
                speech_provider("ollama")

    def test_ollama_url_validation_and_normalization(self):
        for value, expected in [
            ("http://localhost:11434", "http://localhost:11434/v1"),
            ("http://[::1]:11434/", "http://[::1]:11434/v1"),
            ("https://example.com/proxy/v1/", "https://example.com/proxy/v1"),
        ]:
            with self.subTest(value=value), patch.dict(os.environ, {"OLLAMA_BASE_URL": value}, clear=True):
                self.assertEqual(ollama_base_url(), expected)
        for value in ["", "file:///etc/passwd", "http://u:secret@example.com/v1", "https://example.com/v1?key=secret",
                      "http://localhost:bad/v1", "http://localhost:11434/api", "https://bad host/v1"]:
            with self.subTest(value=value), patch.dict(os.environ, {"OLLAMA_BASE_URL": value}, clear=True):
                with self.assertRaises(RuntimeError):
                    ollama_base_url()

    def test_ollama_requires_an_explicit_installed_model(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "ollama", "OLLAMA_BASE_URL": "http://localhost:11434", "OPENAI_API_KEY": "test-openai",
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OLLAMA_MODEL"):
                validate_provider_environment()

    def test_public_config_contains_no_credentials_or_endpoint(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openrouter", "OPENROUTER_API_KEY": "test-secret-should-not-appear",
        }, clear=True):
            config = public_provider_config(validate_provider_environment())
            self.assertEqual(config["dataProcessors"], ["Daily", "OpenRouter"])
            self.assertNotIn("test-secret", json.dumps(config))
            self.assertNotIn("API_KEY", json.dumps(config))


class ProviderAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_initial_greeting_triggers_a_response(self):
        from bot import create_llm
        from pipecat.processors.aggregators.llm_context import LLMContext

        greeting = "Say a short hello and ask how you can help."
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-google"}, clear=True):
            llm = create_llm("gemini")
            llm._session = AsyncMock()
            await llm._handle_context(LLMContext([{"role": "user", "content": greeting}]))

            llm._session.send_client_content.assert_awaited_once()
            request = llm._session.send_client_content.call_args.kwargs
            self.assertTrue(request["turn_complete"])
            self.assertEqual(request["turns"][-1].role, "user")
            self.assertEqual(request["turns"][-1].parts[0].text, greeting)

    async def test_gemini_pipeline_detects_user_speech_for_idle_timeout(self):
        from bot import run_bot
        from pipecat.audio.vad.silero import SileroVADAnalyzer
        from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
        from pipecat.processors.frame_processor import FrameProcessor

        with (
            patch.dict(os.environ, {"AI_PROVIDER": "gemini", "GOOGLE_API_KEY": "test-google"}, clear=True),
            patch("bot.DailyTransport") as transport,
            patch("bot.PipelineWorker"),
            patch("bot.WorkerRunner", return_value=AsyncMock()),
            patch("bot.LLMContextAggregatorPair", wraps=LLMContextAggregatorPair) as aggregators,
        ):
            transport.return_value.input.return_value = FrameProcessor()
            transport.return_value.output.return_value = FrameProcessor()
            await run_bot("https://example.daily.co/test", "test-token")

            user_params = aggregators.call_args.kwargs["user_params"]
            self.assertIsNotNone(user_params)
            self.assertIsInstance(user_params.vad_analyzer, SileroVADAnalyzer)

    async def test_all_five_provider_adapters_construct(self):
        from bot import create_llm

        env = {
            "OPENAI_API_KEY": "test-openai", "GOOGLE_API_KEY": "test-google", "XAI_API_KEY": "test-xai",
            "OPENROUTER_API_KEY": "test-router", "OLLAMA_BASE_URL": "https://ollama.example/v1",
            "OLLAMA_MODEL": "my-local-model", "OLLAMA_API_KEY": "test-ollama", "BOT_PROMPT": "Test instructions",
        }
        expected = {
            "openai": "OpenAIRealtimeLLMService", "gemini": "GeminiLiveLLMService",
            "grok": "GrokRealtimeLLMService", "openrouter": "OpenRouterLLMService", "ollama": "OpenAILLMService",
        }
        with patch.dict(os.environ, env, clear=True):
            for provider, name in expected.items():
                with self.subTest(provider=provider):
                    service = create_llm(provider)
                    self.assertEqual(type(service).__name__, name)
                    client = getattr(service, "_client", None)
                    if isinstance(client, AsyncOpenAI):
                        await client.close()

    async def test_openrouter_stt_uses_router_key_and_multipart_contract(self):
        from bot import create_speech_services

        requests = []

        def handler(request):
            requests.append(request)
            return httpx.Response(200, json={"text": "hello from speech"})

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-router"}, clear=True):
            stt, tts = create_speech_services("openrouter")
            await stt._client.close()
            stt._client = AsyncOpenAI(
                api_key="test-router", base_url="https://openrouter.ai/api/v1",
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
            )
            try:
                audio = io.BytesIO()
                with wave.open(audio, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(b"\0\0" * 1600)
                result = await stt._transcribe(audio.getvalue())
                self.assertEqual(result.text, "hello from speech")
                self.assertEqual(len(requests), 1)
                request = requests[0]
                self.assertEqual(str(request.url), "https://openrouter.ai/api/v1/audio/transcriptions")
                self.assertEqual(request.headers["authorization"], "Bearer test-router")
                self.assertIn("multipart/form-data", request.headers["content-type"])
                self.assertIn(b"openai/whisper-large-v3-turbo", request.content)
                self.assertIn(b"RIFF", request.content)
            finally:
                await stt._client.close()
                await tts._http.aclose()

    async def test_ollama_chat_uses_its_own_endpoint_and_auth(self):
        from bot import create_llm

        with patch.dict(os.environ, {
            "OLLAMA_BASE_URL": "https://ollama.example/v1", "OLLAMA_MODEL": "my-model",
            "OLLAMA_API_KEY": "test-ollama", "OPENAI_API_KEY": "must-not-be-sent",
        }, clear=True):
            llm = create_llm("ollama")
            try:
                self.assertEqual(str(llm._client.base_url), "https://ollama.example/v1/")
                self.assertEqual(llm._client.api_key, "test-ollama")
                self.assertEqual(llm._settings.model, "my-model")
            finally:
                await llm._client.close()

    async def test_openrouter_tts_custom_voice_pcm_and_failure_redaction(self):
        from pipecat.frames.frames import TTSAudioRawFrame
        from speech import OpenRouterTTSService

        for status, content_type, content in [
            (200, "audio/pcm", b"\x01\0\x02\0\x03\0"),
            (401, "application/json", b'{"error":"test-secret-should-not-appear"}'),
            (200, "audio/mpeg", b"not-pcm"),
            (200, "audio/pcm", b"\x01"),
        ]:
            with self.subTest(status=status, content_type=content_type, bytes=len(content)):
                requests = []

                def handler(request):
                    requests.append(request)
                    return httpx.Response(status, headers={"content-type": content_type}, content=content)

                tts = OpenRouterTTSService(api_key="test-router", model="hexgrad/kokoro-82m", voice="af_heart")
                await tts._http.aclose()
                tts._http = httpx.AsyncClient(
                    base_url="https://openrouter.ai/api/v1/", headers={"Authorization": "Bearer test-router"},
                    transport=httpx.MockTransport(handler),
                )
                # PipelineWorker.setup normally initializes the effective sample rate.
                tts._sample_rate = 24000
                tts.push_error = AsyncMock()
                try:
                    frames = [frame async for frame in tts.run_tts("Hello", "test-context")]
                    body = json.loads(requests[0].content)
                    self.assertEqual(body["voice"], "af_heart")
                    self.assertEqual(body["response_format"], "pcm")
                    self.assertEqual(requests[0].headers["authorization"], "Bearer test-router")
                    if status == 200 and content_type == "audio/pcm" and len(content) % 2 == 0:
                        self.assertTrue(all(isinstance(frame, TTSAudioRawFrame) for frame in frames))
                        self.assertEqual(b"".join(frame.audio for frame in frames), content)
                        self.assertEqual(frames[0].sample_rate, 24000)
                    else:
                        tts.push_error.assert_awaited_once_with(
                            "OpenRouter speech generation failed", force_treat_as_permanent=True,
                        )
                        self.assertNotIn("test-secret", str(tts.push_error.call_args))
                finally:
                    await tts._http.aclose()


if __name__ == "__main__":
    unittest.main()
