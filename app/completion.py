from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime, timedelta
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
        backfill_days: int | None = None,
    ) -> None:
        self.client = client
        self.source_channels = list(source_channels)
        self.store = store
        self.process_message = process_message
        self.chat_id_resolver = chat_id_resolver
        self.backfill_days = backfill_days
        self._locks: dict[int, asyncio.Lock] = {}
        self._backfill_applied: set[int] = set()
        self.current_message_id: int | None = None
        self.processed_messages = 0
        self.last_progress_at: str | None = None
        self.channel_statuses: dict[int, dict[str, Any]] = {}
        self._configured_chat_ids: set[int] = set()

    async def initialize(self) -> None:
        """Set a safe starting point for channels that have no checkpoint yet."""
        await self.update_source_channels(self.source_channels)

    async def update_source_channels(self, source_channels: Iterable[str]) -> None:
        new_sources = list(dict.fromkeys(source_channels))
        resolved: list[tuple[str, Any, int, int]] = []
        for source in new_sources:
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
            resolved.append((source, entity, chat_id, checkpoint))

        configured_chat_ids = {item[2] for item in resolved}
        for source, entity, chat_id, checkpoint in resolved:
            self._ensure_channel_status(entity, source, chat_id, checkpoint)
        self.source_channels = new_sources
        self._configured_chat_ids = configured_chat_ids
        for chat_id in list(self.channel_statuses):
            if chat_id not in configured_chat_ids:
                del self.channel_statuses[chat_id]

    def handles_chat(self, entity: Any) -> bool:
        return self.chat_id_resolver(entity) in self._configured_chat_ids

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
                status["pending_messages"] = 0
                return 0

            processed = 0
            source_name = self._source_name(entity, str(source))
            checkpoint = await self._apply_backfill_limit(
                entity, chat_id, source_name, checkpoint
            )
            status = self._ensure_channel_status(
                entity, str(source), chat_id, checkpoint
            )
            status["last_message_id"] = checkpoint
            status["state"] = "syncing"
            status["error"] = None
            status["pending_messages"] = await self._count_pending(
                entity, checkpoint
            )
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
                    if status["pending_messages"] is not None:
                        status["pending_messages"] = max(
                            0, status["pending_messages"] - 1
                        )
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
            status["pending_messages"] = 0
            return processed

    async def _count_pending(self, entity: Any, checkpoint: int) -> int | None:
        try:
            messages = await self.client.get_messages(
                entity, limit=0, min_id=checkpoint
            )
            total = getattr(messages, "total", None)
            return int(total if total is not None else len(messages))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Could not count pending messages for %s: %s",
                self._source_name(entity, str(entity)),
                exc,
            )
            return None

    async def _apply_backfill_limit(
        self, entity: Any, chat_id: int, source_name: str, checkpoint: int
    ) -> int:
        if self.backfill_days is None or chat_id in self._backfill_applied:
            return checkpoint

        cutoff = datetime.now(UTC) - timedelta(days=self.backfill_days)
        messages = await self.client.get_messages(
            entity, limit=1, offset_date=cutoff
        )
        self._backfill_applied.add(chat_id)
        if not messages:
            return checkpoint

        cutoff_message_id = int(messages[0].id)
        if cutoff_message_id <= checkpoint:
            return checkpoint

        await self.store.set(chat_id, source_name, cutoff_message_id)
        logger.info(
            "Advanced checkpoint for %s from %s to %s to enforce a %s-day backfill limit",
            source_name,
            checkpoint,
            cutoff_message_id,
            self.backfill_days,
        )
        return cutoff_message_id

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
                "pending_messages": None,
                "error": None,
            }
            self.channel_statuses[chat_id] = status
        return status

    @staticmethod
    def _source_name(entity: Any, fallback: str) -> str:
        return str(getattr(entity, "username", None) or getattr(entity, "title", None) or fallback)
