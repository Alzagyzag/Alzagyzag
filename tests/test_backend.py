import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from jarvis.config import Settings
from jarvis.main import create_app
from jarvis.providers import OpenAICompatibleProvider, ProviderError


class FakeProvider:
    def __init__(self):
        self.calls = []

    async def stream(self, messages):
        self.calls.append(messages)
        yield "Good morning, "
        yield "sir."


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, api_token="test-token", provider_api_key="test-provider",
                    database_path=str(tmp_path / "jarvis.sqlite3"))


HEADERS = {"Authorization": "Bearer test-token"}


def test_chat_auth_and_persistence(settings):
    provider = FakeProvider()
    sid = str(uuid4())
    with TestClient(create_app(settings, provider)) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        assert client.post("/api/chat", json={"message": "Hello"}).status_code == 401
        response = client.post("/api/chat", headers=HEADERS, json={"message": "Hello", "session_id": sid})
        assert response.status_code == 200
        assert response.json()["message"] == "Good morning, sir."
        assert client.get("/api/diagnostics", headers=HEADERS).json()["metrics"]["disk_free_bytes"] > 0
    with TestClient(create_app(settings, provider)) as client:
        assert len(client.get(f"/api/sessions/{sid}", headers=HEADERS).json()["messages"]) == 2
        client.post("/api/chat", headers=HEADERS, json={"message": "Again", "session_id": sid})
        assert provider.calls[-1][1]["content"] == "Hello"
        assert client.delete(f"/api/sessions/{sid}", headers=HEADERS).status_code == 200
        assert client.get(f"/api/sessions/{sid}", headers=HEADERS).json()["messages"] == []


def test_missing_credentials_startup(settings):
    settings.api_token = SecretStr("")
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        assert client.post("/api/chat", json={"message": "Hello"}).status_code == 503
    settings.api_token = SecretStr("test-token")
    settings.provider_api_key = SecretStr("")
    with TestClient(create_app(settings)) as client:
        response = client.post("/api/chat", headers=HEADERS, json={"message": "Hello"})
        assert response.status_code == 502
        assert "JARVIS_PROVIDER_API_KEY" in response.json()["detail"]


def test_provider_failure_does_not_persist(settings):
    class Failing:
        async def stream(self, messages):
            yield "partial"
            raise ProviderError("Provider connection failed.")
    sid = str(uuid4())
    with TestClient(create_app(settings, Failing())) as client:
        assert client.post("/api/chat", headers=HEADERS, json={"message": "Hi", "session_id": sid}).status_code == 502
        assert client.get(f"/api/sessions/{sid}", headers=HEADERS).json()["messages"] == []


def test_websocket_streaming(settings):
    with TestClient(create_app(settings, FakeProvider())) as client:
        with client.websocket_connect("/ws/assistant") as ws:
            ws.send_json({"type": "auth", "token": "test-token"})
            assert ws.receive_json()["payload"]["status"] == "authenticated"
            ws.send_json({"type": "message.user", "payload": {"message": "Hi"}})
            events = []
            while True:
                event = ws.receive_json()
                events.append(event)
                assert all(key in event for key in ["event_id", "timestamp", "session_id", "correlation_id", "payload"])
                if event["type"] == "assistant.idle":
                    break
            assert "".join(e["payload"]["text"] for e in events if e["type"] == "message.delta") == "Good morning, sir."
            assert len({e["correlation_id"] for e in events}) == 1


def test_websocket_cancel(settings):
    class Slow:
        async def stream(self, messages):
            yield "starting"
            await asyncio.sleep(60)
            yield "finished"
    sid = str(uuid4())
    with TestClient(create_app(settings, Slow())) as client:
        with client.websocket_connect("/ws/assistant") as ws:
            ws.send_json({"type": "auth", "token": "test-token"})
            ws.receive_json()
            ws.send_json({"type": "message.user", "payload": {"message": "Hi", "session_id": sid}})
            while ws.receive_json()["type"] != "message.delta":
                pass
            ws.send_json({"type": "cancel"})
            assert ws.receive_json()["payload"]["status"] == "cancelled"
            assert ws.receive_json()["type"] == "assistant.idle"
        assert client.get(f"/api/sessions/{sid}", headers=HEADERS).json()["messages"] == []


def test_request_validation(settings):
    with TestClient(create_app(settings, FakeProvider())) as client:
        for body in [{"message": ""}, {"message": "x" * 16001}, {"message": "Hi", "session_id": "bad"}]:
            assert client.post("/api/chat", headers=HEADERS, json=body).status_code == 422


def test_provider_requires_secure_url(settings):
    settings.provider_base_url = "http://example.com/v1"
    with pytest.raises(ValueError, match="HTTPS"):
        OpenAICompatibleProvider(settings)


def test_rate_limit(settings):
    with TestClient(create_app(settings, FakeProvider())) as client:
        for _ in range(60):
            assert client.post("/api/chat", headers=HEADERS, json={"message": "Hi"}).status_code == 200
        assert client.post("/api/chat", headers=HEADERS, json={"message": "Hi"}).status_code == 429
