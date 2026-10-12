import httpx
import pytest

from jarvis.config import Settings
from jarvis.providers import OpenAICompatibleProvider, ProviderError


def setup_provider(monkeypatch, response):
    original_client = httpx.AsyncClient
    requests = []

    def respond(request):
        requests.append(request)
        return response

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    provider = OpenAICompatibleProvider(Settings(_env_file=None, provider_api_key="test-key"))
    return provider, requests


@pytest.mark.asyncio
async def test_adapter_sse(monkeypatch):
    response = httpx.Response(200, text='data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n')
    provider, requests = setup_provider(monkeypatch, response)
    assert [p async for p in provider.stream([{"role": "user", "content": "Hi"}])] == ["Hello"]
    assert requests[0].headers["authorization"] == "Bearer test-key"
    assert requests[0].url.path == "/v1/chat/completions"


@pytest.mark.asyncio
@pytest.mark.parametrize("response,reason", [
    (httpx.Response(401, text="secret provider error"), "HTTP 401"),
    (httpx.Response(200, text="data: broken\n\n"), "invalid streaming data"),
    (httpx.Response(200, text='data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'), "completion marker"),
])
async def test_adapter_failures(monkeypatch, response, reason):
    provider, _ = setup_provider(monkeypatch, response)
    with pytest.raises(ProviderError, match=reason) as error:
        _ = [p async for p in provider.stream([])]
    assert "secret provider error" not in str(error.value)
