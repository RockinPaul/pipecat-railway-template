"""One authenticated voice session per process; run exactly one Uvicorn worker."""

import asyncio
import hmac
import json
import logging
import os
import secrets
import sys
import time
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
logger = logging.getLogger("pipecat_starter")
START_TIMEOUT = 60
START_COOLDOWN = 5


@dataclass
class VoiceSession:
    id: str
    expires_at: int
    ready: asyncio.Future
    task: asyncio.Task | None = None
    process: asyncio.subprocess.Process | None = None
    cleaning_up: bool = False


def required_secret(name: str) -> str:
    value = os.getenv(name, "")
    if not value or any(char.isspace() for char in value):
        raise RuntimeError(f"{name} must be set and contain no whitespace")
    return value


async def stop_session(session: VoiceSession) -> None:
    if session.task and not session.task.done():
        if not session.task.cancelling() and not session.cleaning_up:
            session.task.cancel()
        with suppress(asyncio.CancelledError):
            await asyncio.shield(session.task)


@asynccontextmanager
async def lifespan(app: FastAPI):
    password = required_secret("ACCESS_PASSWORD")
    if len(password) < 24:
        raise RuntimeError("ACCESS_PASSWORD must contain at least 24 characters")
    required_secret("OPENAI_API_KEY")
    daily_key = required_secret("DAILY_API_KEY")
    duration = int(os.getenv("MAX_SESSION_SECONDS", "600"))
    if not 30 <= duration <= 1800:
        raise RuntimeError("MAX_SESSION_SECONDS must be between 30 and 1800")
    if not (ROOT / "static" / "app.js").is_file():
        raise RuntimeError("Browser bundle missing; run npm ci and npm run build")
    app.state.password = password.encode()
    app.state.duration = duration
    app.state.session = None
    app.state.last_start = float("-inf")
    app.state.shutting_down = False
    async with httpx.AsyncClient(
        base_url="https://api.daily.co/v1/",
        headers={"Authorization": f"Bearer {daily_key}"},
        timeout=10,
    ) as daily:
        app.state.daily = daily
        try:
            yield
        finally:
            app.state.shutting_down = True
            if app.state.session:
                await stop_session(app.state.session)


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(self)"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://c.daily.co/call-machine/versioned/0.92.2/static/ "
        "https://c.dailywebrtc.com/call-machine/versioned/0.92.2/static/ "
        "https://c.dailywebrtc.net/call-machine/versioned/0.92.2/static/; style-src 'self'; "
        "connect-src 'self' https://*.daily.co wss://*.daily.co "
        "https://*.dailywebrtc.com wss://*.dailywebrtc.com https://*.dailywebrtc.net wss://*.dailywebrtc.net; "
        "frame-src https://*.daily.co; worker-src 'self' blob: https://c.daily.co "
        "https://c.dailywebrtc.com https://c.dailywebrtc.net; "
        "img-src 'self' data:; media-src 'self' blob:; "
        "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    return response


async def authenticate(authorization: str = Header(default="")):
    supplied = authorization.removeprefix("Bearer ")
    if (
        not authorization.startswith("Bearer ")
        or len(supplied) > 4096
        or not hmac.compare_digest(supplied.encode(), app.state.password)
    ):
        raise HTTPException(401, "Check your access password and try again.")


async def daily_post(path: str, body: dict) -> dict:
    response = await app.state.daily.post(path, json=body)
    response.raise_for_status()
    return response.json()


async def run_session(session: VoiceSession):
    room_name = f"pipecat-{session.id}"
    try:
        room = await daily_post("rooms", {
            "name": room_name,
            "privacy": "private",
            "properties": {
                "exp": session.expires_at,
                "eject_at_room_exp": True,
                "max_participants": 2,
                "start_video_off": True,
                "enable_chat": False,
            },
        })
        tokens = []
        for owner, name in [(True, "Voice assistant"), (False, "You")]:
            token = await daily_post("meeting-tokens", {"properties": {
                "room_name": room_name,
                "exp": session.expires_at,
                "eject_at_token_exp": True,
                "is_owner": owner,
                "user_name": name,
                "start_video_off": True,
            }})
            tokens.append(token["token"])
        # Pass the room token over stdin, never in command arguments or logs.
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "bot.py"),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            env={key: value for key, value in os.environ.items()
                 if key not in {"DAILY_API_KEY", "ACCESS_PASSWORD"}},
        ))
        try:
            session.process = await asyncio.shield(spawn)
        except asyncio.CancelledError:
            session.process = await spawn
            raise
        session.process.stdin.write(json.dumps({
            "room_url": room["url"], "token": tokens[0],
        }).encode() + b"\n")
        await session.process.stdin.drain()
        session.process.stdin.close()
        # Only hand the browser a room once the bot has actually joined it.
        while True:
            line = await session.process.stdout.readline()
            if not line:
                raise RuntimeError("Bot exited before joining the room")
            if line.strip() == b"PIPECAT_READY":
                break
        session.ready.set_result({
            "id": session.id, "url": room["url"], "token": tokens[1],
            "expiresAt": session.expires_at,
        })
        logger.info("Voice session started")
        # Room/token expiry also caps cost if this process is forcefully stopped.
        remaining = max(0, session.expires_at - time.time())
        with suppress(TimeoutError):
            await asyncio.wait_for(session.process.wait(), timeout=remaining)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        # Provider exception bodies can contain tokens or request details.
        logger.error("Voice session failed (%s)", type(error).__name__)
    finally:
        session.cleaning_up = True
        if session.process and session.process.returncode is None:
            with suppress(ProcessLookupError):
                session.process.terminate()
            try:
                await asyncio.wait_for(session.process.wait(), timeout=5)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    session.process.kill()
                await session.process.wait()
        try:
            response = await app.state.daily.delete(f"rooms/{room_name}")
            if response.status_code != 404:
                response.raise_for_status()
        except Exception as error:
            logger.warning("Room cleanup failed (%s); expiry remains active", type(error).__name__)
        if app.state.session is session:
            app.state.session = None
        if not session.ready.done():
            session.ready.set_exception(RuntimeError("Voice session could not start"))
        logger.info("Voice session finished")


@app.get("/health")
async def health():
    if app.state.shutting_down:
        raise HTTPException(503, "Shutting down")
    return {"status": "ready"}


@app.post("/api/auth", dependencies=[Depends(authenticate)], status_code=204)
async def auth():
    return Response(status_code=204)


@app.post("/api/start", dependencies=[Depends(authenticate)])
async def start_session():
    if app.state.shutting_down:
        raise HTTPException(503, "The app is restarting. Try again shortly.")
    # ponytail: one slot in one process; add a shared dispatcher before replicas.
    if app.state.session is not None:
        raise HTTPException(429, "A conversation is already active. Try again when it ends.")
    if time.monotonic() - app.state.last_start < START_COOLDOWN:
        raise HTTPException(429, "Wait a few seconds before starting another conversation.")
    app.state.last_start = time.monotonic()
    session = VoiceSession(
        id=secrets.token_hex(16),
        expires_at=int(time.time()) + app.state.duration,
        ready=asyncio.get_running_loop().create_future(),
    )
    # Reserve the slot before the first await so simultaneous requests cannot race.
    app.state.session = session
    session.task = asyncio.create_task(run_session(session))
    try:
        return await asyncio.wait_for(asyncio.shield(session.ready), START_TIMEOUT)
    except (TimeoutError, RuntimeError):
        await stop_session(session)
        # Retrieve a late exception after a startup timeout to avoid orphan warnings.
        if session.ready.done() and not session.ready.cancelled():
            session.ready.exception()
        raise HTTPException(502, "The voice service could not start. Check the provider keys and service logs.") from None
    except asyncio.CancelledError:
        await stop_session(session)
        if session.ready.done() and not session.ready.cancelled():
            session.ready.exception()
        raise


@app.get("/api/sessions/{session_id}", dependencies=[Depends(authenticate)])
async def session_status(session_id: str):
    current = app.state.session
    if current is None or current.id != session_id:
        return {"status": "ended"}
    return {"status": "active", "expiresAt": current.expires_at}


@app.delete("/api/sessions/{session_id}", dependencies=[Depends(authenticate)], status_code=204)
async def end_session(session_id: str):
    current = app.state.session
    if current is not None and current.id == session_id:
        await stop_session(current)
    return Response(status_code=204)


app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="client")


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")),
                access_log=False, timeout_graceful_shutdown=20)
