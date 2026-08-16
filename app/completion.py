from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from app.checkpoints import CheckpointStore
from app.time_utils import israel_now

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
        self.channel_statuses: dict[int, dict[str, Any]] = {}

    async def initialize(self) -> None:
        """Set a safe starting point for channels that have no checkpoint yet."""
        for source in self.source_channels:
            entity = await self.client.get_entity(source)
            chat_id = self.chat_id_resolver(entity)
            checkpoint = await self.store.get(chat_id)
            if checkpoint is None:
                latest = await self.client.get_messages(entity, limit=1)
                checkpoint = int(latest[0].id) if latest else 0
                await self.store.set(
                    chat_id, self._source_name(entity, source), checkpoint
                )
                logger.info(
                    "Initialized checkpoint for %s at message %s", source, checkpoint
                )

            self._ensure_channel_status(entity, source, chat_id, checkpoint)

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
                status = self._ensure_channel_status(
                    entity, str(source), chat_id, latest_id
                )
                status["state"] = "ready"
                status["last_checked_at"] = israel_now()
                return 0

            processed = 0
            source_name = self._source_name(entity, str(source))
            status = self._ensure_channel_status(
                entity, str(source), chat_id, checkpoint
            )
            status["state"] = "syncing"
            status["error"] = None
            try:
                async for message in self.client.iter_messages(
                    entity, min_id=checkpoint, reverse=True
                ):
                    self.current_message_id = int(message.id)
                    status["current_message_id"] = int(message.id)
                    await self.process_message(message)
                    await self.store.set(chat_id, source_name, int(message.id))
                    processed += 1
                    self.processed_messages += 1
                    self.last_progress_at = israel_now()
                    status["last_message_id"] = int(message.id)
                    status["last_processed_at"] = self.last_progress_at
                    status["processed_messages"] += 1
            except Exception as exc:
                status["state"] = "error"
                status["error"] = f"{type(exc).__name__}: {exc}"
                status["last_checked_at"] = israel_now()
                raise

            if processed:
                logger.info("Completed %s missing messages for %s", processed, source_name)
            self.current_message_id = None
            status["current_message_id"] = None
            status["last_checked_at"] = israel_now()
            status["state"] = "ready"
            return processed

    def health_channels(self) -> dict[str, dict[str, Any]]:
        return {
            str(status["configured_source"]): {
                key: value
                for key, value in status.items()
                if key != "configured_source"
            }
            for status in self.channel_statuses.values()
        }

    def _ensure_channel_status(
        self,
        entity: Any,
        configured_source: str,
        chat_id: int,
        checkpoint: int,
    ) -> dict[str, Any]:
        status = self.channel_statuses.get(chat_id)
        if status is None:
            status = {
                "configured_source": configured_source,
                "source_channel": self._source_name(entity, configured_source),
                "source_chat_id": chat_id,
                "state": "initialized",
                "last_message_id": checkpoint,
                "current_message_id": None,
                "last_checked_at": None,
                "last_processed_at": None,
                "processed_messages": 0,
                "error": None,
            }
            self.channel_statuses[chat_id] = status
        return status

    @staticmethod
    def _source_name(entity: Any, fallback: str) -> str:
        return str(getattr(entity, "username", None) or getattr(entity, "title", None) or fallback)
