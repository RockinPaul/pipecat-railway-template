"""Offline regression checks for authentication, billable resources, and cleanup."""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

import server


class FakeBot:
    def __init__(self, output=b"PIPECAT_READY\n"):
        self.returncode = None
        self.exited = asyncio.Event()
        self.stdin = Mock(drain=AsyncMock())
        self.stdout = asyncio.StreamReader()
        if output:
            self.stdout.feed_data(output)

    async def wait(self):
        await self.exited.wait()
        return self.returncode

    def terminate(self):
        self.returncode = 0
        self.exited.set()

    kill = terminate


class VoiceServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.env = patch.dict(os.environ, {
            "ACCESS_PASSWORD": "offline-test-password-123456789",
            "DAILY_API_KEY": "offline-daily-key",
            "OPENAI_API_KEY": "offline-openai-key",
            "MAX_SESSION_SECONDS": "600",
        })
        self.env.start()
        self.bot = FakeBot()
        self.spawn = patch("server.asyncio.create_subprocess_exec", AsyncMock(return_value=self.bot))
        self.spawn_mock = self.spawn.start()
        self.requests = []
        self.block_room = None
        self.fail_path = None
        self.lifespan = server.app.router.lifespan_context(server.app)
        await self.lifespan.__aenter__()
        self.daily = httpx.AsyncClient(
            base_url="https://api.daily.co/v1/",
            transport=httpx.MockTransport(self.daily_response),
        )
        server.app.state.daily = self.daily
        self.client = httpx.AsyncClient(
            base_url="http://test", transport=httpx.ASGITransport(app=server.app),
            headers={"Authorization": "Bearer offline-test-password-123456789"},
        )

    async def asyncTearDown(self):
        await self.lifespan.__aexit__(None, None, None)
        await self.client.aclose()
        await self.daily.aclose()
        self.spawn.stop()
        self.env.stop()

    async def daily_response(self, request):
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if self.fail_path == request.url.path:
            return httpx.Response(401, json={"error": "private-provider-error-body"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"deleted": True})
        if request.url.path == "/v1/rooms":
            if self.block_room:
                await self.block_room.wait()
            return httpx.Response(200, json={"url": f"https://example.daily.co/{body['name']}"})
        return httpx.Response(200, json={"token": "bot-only-token" if body["properties"]["is_owner"] else "user-only-token"})

    async def test_health_and_auth_do_not_create_resources(self):
        self.assertEqual((await self.client.get("/health")).json(), {"status": "ready"})
        self.assertEqual((await self.client.post("/api/auth")).status_code, 204)
        self.assertEqual(self.requests, [])
        self.spawn_mock.assert_not_called()

    async def test_control_routes_require_auth_and_do_not_echo_passwords(self):
        for method, path in [("POST", "/api/auth"), ("POST", "/api/start"),
                             ("GET", "/api/sessions/unknown"), ("DELETE", "/api/sessions/unknown")]:
            response = await self.client.request(method, path, headers={"Authorization": "Bearer wrong"})
            self.assertEqual(response.status_code, 401)
            self.assertNotIn("wrong", response.text)
        self.assertEqual(self.requests, [])

    async def test_private_expiring_room_and_least_privilege_browser_token(self):
        response = await self.client.post("/api/start")
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["token"], "user-only-token")
        self.assertNotIn("bot-only-token", response.text)
        room = self.requests[0][2]
        self.assertEqual(room["privacy"], "private")
        self.assertEqual(room["properties"]["max_participants"], 2)
        self.assertTrue(room["properties"]["eject_at_room_exp"])
        self.assertEqual(room["properties"]["exp"], payload["expiresAt"])
        for _, _, body in self.requests[1:3]:
            self.assertEqual(body["properties"]["room_name"], room["name"])
            self.assertTrue(body["properties"]["eject_at_token_exp"])
        args, kwargs = self.spawn_mock.call_args
        self.assertNotIn("bot-only-token", str(args))
        self.assertNotIn("ACCESS_PASSWORD", kwargs["env"])
        self.assertNotIn("DAILY_API_KEY", kwargs["env"])
        self.assertEqual(json.loads(self.bot.stdin.write.call_args.args[0])["token"], "bot-only-token")

    async def test_simultaneous_start_reserves_single_slot_before_network(self):
        self.block_room = asyncio.Event()
        first = asyncio.create_task(self.client.post("/api/start"))
        for _ in range(100):
            if self.requests:
                break
            await asyncio.sleep(0.001)
        try:
            second = await self.client.post("/api/start")
            self.assertEqual(second.status_code, 429)
            self.assertEqual(len(self.requests), 1)
        finally:
            self.block_room.set()
            self.assertEqual((await first).status_code, 200)

    async def test_stop_is_scoped_idempotent_and_reclaims_room(self):
        payload = (await self.client.post("/api/start")).json()
        await self.client.delete("/api/sessions/wrong-session")
        self.assertIsNone(self.bot.returncode)
        for _ in range(2):
            response = await self.client.delete(f"/api/sessions/{payload['id']}")
            self.assertEqual(response.status_code, 204)
        self.assertEqual(self.bot.returncode, 0)
        self.assertIsNone(server.app.state.session)
        self.assertTrue(any(method == "DELETE" for method, _, _ in self.requests))
        self.assertEqual((await self.client.get(f"/api/sessions/{payload['id']}")).json(), {"status": "ended"})

    async def test_reconnect_after_cleanup(self):
        first = (await self.client.post("/api/start")).json()
        await self.client.delete(f"/api/sessions/{first['id']}")
        server.app.state.last_start -= 10
        self.bot = FakeBot()
        self.spawn_mock.return_value = self.bot
        second = await self.client.post("/api/start")
        self.assertEqual(second.status_code, 200)
        self.assertNotEqual(first["id"], second.json()["id"])

    async def test_provider_failure_releases_slot_and_hides_provider_body(self):
        self.fail_path = "/v1/meeting-tokens"
        response = await self.client.post("/api/start")
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private-provider-error-body", response.text)
        for _ in range(100):
            if server.app.state.session is None:
                break
            await asyncio.sleep(0.001)
        self.assertIsNone(server.app.state.session)
        self.assertTrue(any(method == "DELETE" for method, _, _ in self.requests))
        self.spawn_mock.assert_not_called()

    async def test_bot_start_timeout_stops_process_and_releases_slot(self):
        self.bot = FakeBot(output=b"")
        self.spawn_mock.return_value = self.bot
        with patch("server.START_TIMEOUT", 0.02):
            response = await self.client.post("/api/start")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(self.bot.returncode, 0)
        self.assertIsNone(server.app.state.session)

    async def test_bot_crash_before_readiness_fails_start(self):
        self.bot = FakeBot(output=b"")
        self.bot.stdout.feed_eof()
        self.spawn_mock.return_value = self.bot
        response = await self.client.post("/api/start")
        self.assertEqual(response.status_code, 502)
        self.assertIsNone(server.app.state.session)

    async def test_bot_exit_cleans_up_without_browser_stop(self):
        await self.client.post("/api/start")
        task = server.app.state.session.task
        self.bot.terminate()
        await task
        self.assertIsNone(server.app.state.session)

    async def test_cooldown_blocks_rapid_paid_session_creation(self):
        payload = (await self.client.post("/api/start")).json()
        await self.client.delete(f"/api/sessions/{payload['id']}")
        count = len(self.requests)
        self.assertEqual((await self.client.post("/api/start")).status_code, 429)
        self.assertEqual(len(self.requests), count)

    async def test_static_client_security_headers_and_no_secret_exposure(self):
        response = await self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        policy = dict(
            directive.strip().split(" ", 1)
            for directive in response.headers["content-security-policy"].split(";")
            if directive.strip()
        )
        daily_version = json.loads((server.ROOT / "package.json").read_text())["dependencies"]["@daily-co/daily-js"]
        script_sources = policy["script-src"].split()
        self.assertNotIn("'unsafe-eval'", script_sources)
        self.assertNotIn("'unsafe-inline'", script_sources)
        for host in ["c.daily.co", "c.dailywebrtc.com", "c.dailywebrtc.net"]:
            self.assertIn(f"https://{host}/call-machine/versioned/{daily_version}/static/", script_sources)
        self.assertNotIn("offline-openai-key", response.text)
        self.assertEqual((await self.client.get("/.env")).status_code, 404)
        self.assertEqual((await self.client.get("/server.py")).status_code, 404)

    async def test_invalid_configuration_fails_before_readiness(self):
        for bad in ["", " has-leading-space", "embedded space", "trailing\n"]:
            with patch.dict(os.environ, {"DAILY_API_KEY": bad}):
                with self.assertRaises(RuntimeError):
                    server.required_secret("DAILY_API_KEY")
        with patch.dict(os.environ, {"ACCESS_PASSWORD": "short"}):
            with self.assertRaises(RuntimeError):
                async with server.lifespan(server.app):
                    self.fail("Invalid password unexpectedly passed startup")


if __name__ == "__main__":
    unittest.main()
