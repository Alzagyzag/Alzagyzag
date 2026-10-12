import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from jarvis.config import Settings
from jarvis.providers import Provider, ProviderError
from jarvis.storage import Store


class Assistant:
    def __init__(self, settings: Settings, provider: Provider, store: Store):
        self.settings, self.provider, self.store = settings, provider, store
        self.capacity = asyncio.Semaphore(settings.max_concurrent_requests)
        self.locks: dict[str, tuple[asyncio.Lock, int]] = {}

    @asynccontextmanager
    async def session_guard(self, session: str):
        lock, count = self.locks.get(session, (asyncio.Lock(), 0))
        self.locks[session] = (lock, count + 1)
        try:
            async with lock:
                yield
        finally:
            _, count = self.locks[session]
            if count == 1:
                del self.locks[session]
            else:
                self.locks[session] = (lock, count - 1)

    async def stream(self, session: str, text: str) -> AsyncIterator[str]:
        async with self.capacity, self.session_guard(session):
            history = await self.store.read(session)
            messages = [{"role": "system", "content": self.settings.personality}]
            messages += history[-self.settings.max_context_messages:] + [{"role": "user", "content": text}]
            parts: list[str] = []
            try:
                async with asyncio.timeout(self.settings.request_timeout_seconds):
                    async for part in self.provider.stream(messages):
                        parts.append(part)
                        if sum(map(len, parts)) > 100_000:
                            raise ProviderError("Provider response exceeded the configured safety limit.")
                        yield part
            except TimeoutError as exc:
                raise ProviderError("Assistant request timed out.") from exc
            if not parts or not "".join(parts).strip():
                raise ProviderError("Provider returned an empty response.")
            history += [{"role": "user", "content": text}, {"role": "assistant", "content": "".join(parts)}]
            await self.store.save(session, history)
