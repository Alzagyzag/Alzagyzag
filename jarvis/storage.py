"""Persistent sessions; only completed exchanges are committed."""
import json
from pathlib import Path

import aiosqlite


class Store:
    def __init__(self, path: str):
        self.path = path

    async def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, messages TEXT NOT NULL)")
            await db.commit()

    async def read(self, session: str) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT messages FROM sessions WHERE id=?", (session,)) as cursor:
                row = await cursor.fetchone()
                return json.loads(row[0]) if row else []

    async def save(self, session: str, messages: list[dict[str, str]]) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("INSERT INTO sessions VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET messages=excluded.messages",
                             (session, json.dumps(messages)))
            await db.commit()

    async def delete(self, session: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM sessions WHERE id=?", (session,))
            await db.commit()

    async def healthy(self) -> bool:
        async with aiosqlite.connect(self.path) as db:
            await db.execute("SELECT id FROM sessions LIMIT 1")
        return True
