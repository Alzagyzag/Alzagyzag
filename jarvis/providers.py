"""Replaceable provider interface and verified HTTP streaming adapter."""
import json
from collections.abc import AsyncIterator
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from jarvis.config import Settings


class ProviderError(Exception):
    """Safe error message suitable for client responses."""


class Provider(Protocol):
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings):
        self.settings = settings
        url = urlsplit(settings.provider_base_url)
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Provider URL must not contain credentials, query or fragment.")
        if not url.hostname or (url.scheme != "https" and not (url.scheme == "http" and local)):
            raise ValueError("Provider URL requires HTTPS, except for loopback local models.")

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        if self.settings.provider != "ollama" and not self.settings.provider_api_key.get_secret_value():
            raise ProviderError("Selected provider requires JARVIS_PROVIDER_API_KEY.")
        headers = {}
        key = self.settings.provider_api_key.get_secret_value()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        endpoint = self.settings.provider_base_url.rstrip("/") + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                async with client.stream("POST", endpoint, headers=headers, json={
                    "model": self.settings.model, "messages": messages, "stream": True,
                }) as response:
                    if response.status_code != 200:
                        raise ProviderError(f"Provider returned HTTP {response.status_code}.")
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            event = json.loads(payload)
                            if "error" in event:
                                raise ProviderError("Provider reported a streaming error.")
                            choices = event.get("choices", [])
                            if choices:
                                content = choices[0].get("delta", {}).get("content")
                                if content:
                                    if not isinstance(content, str):
                                        raise ProviderError("Provider returned invalid text content.")
                                    yield content
                                if choices[0].get("finish_reason"):
                                    return
                        except (ValueError, TypeError, AttributeError, IndexError) as exc:
                            raise ProviderError("Provider returned invalid streaming data.") from exc
                    raise ProviderError("Provider stream ended without a completion marker.")
        except httpx.TimeoutException as exc:
            raise ProviderError("Provider request timed out.") from exc
        except httpx.HTTPError as exc:
            raise ProviderError("Provider connection failed.") from exc
