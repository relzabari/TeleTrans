from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timezone
from typing import Any

from app.checkpoints import CheckpointStore

logger = logging.getLogger(__name__)

ProcessMessage = Callable[[Any], Awaitable[None]]
ChatIdResolver = Callable[[Any], int]


def telegram_chat_id(entity: Any) -> int:
    from telethon import utils

    return utils.get_peer_id(entity)


class CompletionManager:
    def __init__(
        self,
        client: Any,
        source_channels: Iterable[str],
        store: CheckpointStore,
        process_message: ProcessMessage,
        chat_id_resolver: ChatIdResolver = telegram_chat_id,
    ) -> None:
        self.client = client
        self.source_channels = list(source_channels)
        self.store = store
        self.process_message = process_message
        self.chat_id_resolver = chat_id_resolver
        self._locks: dict[int, asyncio.Lock] = {}
        self.current_message_id: int | None = None
        self.processed_messages = 0
        self.last_progress_at: str | None = None

    async def initialize(self) -> None:
        """Set a safe starting point for channels that have no checkpoint yet."""
        for source in self.source_channels:
            entity = await self.client.get_entity(source)
            chat_id = self.chat_id_resolver(entity)
            if await self.store.get(chat_id) is not None:
                continue

            latest = await self.client.get_messages(entity, limit=1)
            latest_id = int(latest[0].id) if latest else 0
            await self.store.set(chat_id, self._source_name(entity, source), latest_id)
            logger.info("Initialized checkpoint for %s at message %s", source, latest_id)

    async def sync_all(self) -> None:
        for source in self.source_channels:
            await self.sync_channel(source)

    async def sync_channel(self, source: Any) -> int:
        entity = await self.client.get_entity(source)
        chat_id = self.chat_id_resolver(entity)
        lock = self._locks.setdefault(chat_id, asyncio.Lock())

        async with lock:
            checkpoint = await self.store.get(chat_id)
            if checkpoint is None:
                latest = await self.client.get_messages(entity, limit=1)
                latest_id = int(latest[0].id) if latest else 0
                await self.store.set(chat_id, self._source_name(entity, str(source)), latest_id)
                return 0

            processed = 0
            source_name = self._source_name(entity, str(source))
            async for message in self.client.iter_messages(
                entity, min_id=checkpoint, reverse=True
            ):
                self.current_message_id = int(message.id)
                await self.process_message(message)
                await self.store.set(chat_id, source_name, int(message.id))
                processed += 1
                self.processed_messages += 1
                self.last_progress_at = datetime.now(timezone.utc).isoformat()

            if processed:
                logger.info("Completed %s missing messages for %s", processed, source_name)
            self.current_message_id = None
            return processed

    @staticmethod
    def _source_name(entity: Any, fallback: str) -> str:
        return str(getattr(entity, "username", None) or getattr(entity, "title", None) or fallback)
