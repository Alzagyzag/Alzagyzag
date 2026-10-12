import asyncio
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import psutil
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from jarvis.assistant import Assistant
from jarvis.config import Settings, get_settings
from jarvis.providers import OpenAICompatibleProvider, Provider, ProviderError
from jarvis.storage import Store


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=16000)
    session_id: UUID = Field(default_factory=uuid4)


class ChatResponse(BaseModel):
    session_id: UUID
    message: str


def create_app(settings: Settings | None = None, provider: Provider | None = None) -> FastAPI:
    settings = settings or get_settings()
    store = Store(settings.database_path)
    assistant = Assistant(settings, provider or OpenAICompatibleProvider(settings), store)
    recent: deque[float] = deque()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.initialize()
        yield

    app = FastAPI(title="J.A.R.V.I.S.", version="0.1.0", lifespan=lifespan)
    app.state.assistant = assistant
    interface = Path(__file__).parent / "web"
    app.mount("/assets", StaticFiles(directory=interface), name="assets")

    @app.get("/", include_in_schema=False)
    async def dashboard():
        return FileResponse(interface / "index.html", headers={"Cache-Control": "no-store"})

    security = HTTPBearer(auto_error=False)

    def check_token(token: str | None):
        expected = settings.api_token.get_secret_value()
        if not expected:
            raise HTTPException(503, "JARVIS_API_TOKEN must be configured.")
        if not token or not secrets.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(401, "Invalid or missing bearer token.")

    def rate_limit():
        now = time.monotonic()
        while recent and recent[0] <= now - 60:
            recent.popleft()
        if len(recent) >= 60:
            raise HTTPException(429, "Assistant request limit reached; retry later.")
        recent.append(now)

    async def authorized(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
        check_token(credentials.credentials if credentials else None)

    @app.get("/healthz")
    async def health():
        try:
            await store.healthy()
        except Exception:
            raise HTTPException(503, "Database unavailable.") from None
        return {"status": "ok", "phase": 1}

    @app.get("/api/status", dependencies=[Depends(authorized)])
    async def status():
        return {"phase": 1, "provider": settings.provider, "model": settings.model,
                "chat_configured": settings.unavailable_reason() is None,
                "configuration_issue": settings.unavailable_reason(),
                "provider_connectivity": "not_checked",
                "capabilities": ["text_chat", "websocket_streaming", "conversation_persistence"],
                "unavailable": ["voice", "tools", "semantic_memory", "automation", "external_integrations"]}

    @app.get("/api/diagnostics", dependencies=[Depends(authorized)])
    async def diagnostics():
        database_ok = True
        try:
            await store.healthy()
        except Exception:
            database_ok = False
        metrics = await asyncio.to_thread(lambda: {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_free_bytes": psutil.disk_usage(str(Path(settings.database_path).parent)).free,
        })
        return {"database": "ok" if database_ok else "failed", "metrics": metrics,
                "provider_connectivity": "not_checked", "configuration_issue": settings.unavailable_reason()}

    @app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(authorized)])
    async def chat(body: ChatRequest, request: Request):
        rate_limit()
        result: list[str] = []
        async def generate():
            async for part in assistant.stream(str(body.session_id), body.message):
                result.append(part)
        task = asyncio.create_task(generate())
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=0.1)
                if await request.is_disconnected():
                    task.cancel()
                    raise HTTPException(499, "Client disconnected.")
            await task
        except ProviderError as exc:
            raise HTTPException(502, str(exc)) from None
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError):
                if task.cancelled() or not task.done():
                    await task
        return ChatResponse(session_id=body.session_id, message="".join(result))

    @app.get("/api/sessions/{session_id}", dependencies=[Depends(authorized)])
    async def session(session_id: UUID):
        return {"session_id": session_id, "messages": await store.read(str(session_id))}

    @app.delete("/api/sessions/{session_id}", dependencies=[Depends(authorized)])
    async def delete_session(session_id: UUID):
        async with assistant.session_guard(str(session_id)):
            await store.delete(str(session_id))
        return {"deleted": True}

    @app.websocket("/ws/assistant")
    async def websocket(ws: WebSocket):
        # Authenticate via first frame so browser clients need no URL credentials.
        await ws.accept()
        task: asyncio.Task | None = None
        send_lock = asyncio.Lock()

        async def send(kind: str, payload: dict, session_id: str | None = None, correlation_id: str | None = None):
            async with send_lock:
                await ws.send_json({"type": kind, "event_id": str(uuid4()),
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "session_id": session_id, "correlation_id": correlation_id, "payload": payload})

        async def respond(body: ChatRequest, correlation_id: str):
            session_id = str(body.session_id)
            try:
                await send("assistant.thinking", {}, session_id, correlation_id)
                parts = []
                async for part in assistant.stream(session_id, body.message):
                    parts.append(part)
                    await send("message.delta", {"text": part}, session_id, correlation_id)
                await send("message.assistant", {"text": "".join(parts)}, session_id, correlation_id)
            except ProviderError as exc:
                await send("system.error", {"message": str(exc)}, session_id, correlation_id)
            except asyncio.CancelledError:
                await send("system.status", {"status": "cancelled"}, session_id, correlation_id)
                raise
            except Exception:
                await send("system.error", {"message": "Assistant request failed."}, session_id, correlation_id)
            finally:
                await send("assistant.idle", {}, session_id, correlation_id)

        try:
            auth = await asyncio.wait_for(ws.receive_json(), timeout=10)
            if not isinstance(auth, dict) or auth.get("type") != "auth" or not isinstance(auth.get("token"), str):
                await ws.close(code=1008)
                return
            try:
                check_token(auth["token"])
            except HTTPException:
                await ws.close(code=1008)
                return
            await send("system.status", {"status": "authenticated"})
            while True:
                event = await ws.receive_json()
                if not isinstance(event, dict):
                    await send("system.error", {"message": "Expected an event object."})
                    continue
                if event.get("type") == "cancel":
                    if task and not task.done():
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                    continue
                if event.get("type") != "message.user":
                    await send("system.error", {"message": "Unsupported event type."})
                    continue
                if task and not task.done():
                    await send("system.warning", {"message": "A response is already active; cancel it first."})
                    continue
                try:
                    body = ChatRequest.model_validate(event.get("payload", {}))
                    rate_limit()
                except (ValidationError, HTTPException):
                    await send("system.error", {"message": "Invalid chat payload or request limit exceeded."})
                    continue
                task = asyncio.create_task(respond(body, str(uuid4())))
        except (WebSocketDisconnect, TimeoutError, ValueError):
            pass
        finally:
            if task:
                if not task.done():
                    task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task

    return app


app = create_app()
