from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol


class CheckpointStore(Protocol):
    async def get(self, source_chat_id: int) -> int | None: ...

    async def set(self, source_chat_id: int, source_channel: str, message_id: int) -> None: ...


class FileCheckpointStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def get(self, source_chat_id: int) -> int | None:
        async with self._lock:
            data = self._read()
            value = data.get(str(source_chat_id))
            return int(value["last_message_id"]) if value else None

    async def set(self, source_chat_id: int, source_channel: str, message_id: int) -> None:
        async with self._lock:
            data = self._read()
            data[str(source_chat_id)] = {
                "source_channel": source_channel,
                "last_message_id": message_id,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temporary_path.replace(self.path)

    def _read(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


class SupabaseCheckpointStore:
    def __init__(self, url: str, key: str) -> None:
        from supabase import create_client

        self.client = create_client(url, key)

    async def get(self, source_chat_id: int) -> int | None:
        def query() -> int | None:
            response = (
                self.client.table("channel_checkpoints")
                .select("last_message_id")
                .eq("source_chat_id", source_chat_id)
                .limit(1)
                .execute()
            )
            return int(response.data[0]["last_message_id"]) if response.data else None

        return await asyncio.to_thread(query)

    async def set(self, source_chat_id: int, source_channel: str, message_id: int) -> None:
        def upsert() -> None:
            (
                self.client.table("channel_checkpoints")
                .upsert(
                    {
                        "source_chat_id": source_chat_id,
                        "source_channel": source_channel,
                        "last_message_id": message_id,
                    },
                    on_conflict="source_chat_id",
                )
                .execute()
            )

        await asyncio.to_thread(upsert)
