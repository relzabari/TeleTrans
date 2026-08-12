from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from app.checkpoints import FileCheckpointStore, SupabaseCheckpointStore
from app.completion import CompletionManager
from app.config import BotConfig, load_config
from app.telegram_client import (
    create_client,
    process_message,
    register_handlers,
    resolve_destination,
    start_client,
)

logger = logging.getLogger(__name__)


class BotRuntime:
    def __init__(self) -> None:
        self.status = "stopped"
        self.last_error: str | None = None
        self.started_at: str | None = None
        self.last_synced_at: str | None = None
        self.client: Any = None
        self.completion: CompletionManager | None = None
        self.task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if self.task and not self.task.done():
            return
        self._stopping = False
        self.status = "starting"
        self.last_error = None
        self.started_at = self._now()
        self.task = asyncio.create_task(self._run(), name="telegram-runtime")

    async def stop(self) -> None:
        self._stopping = True
        if self.client and self.client.is_connected():
            await self.client.disconnect()

        if self.task and not self.task.done():
            self.task.cancel()
            with suppress(asyncio.CancelledError):
                await self.task
        self.status = "stopped"

    async def wait(self) -> None:
        if self.task:
            await self.task
        if self.status == "error":
            raise RuntimeError(self.last_error or "Telegram runtime failed")

    def health(self) -> dict[str, str | int | None]:
        health: dict[str, str | int | None] = {
            "status": self.status,
            "started_at": self.started_at,
            "last_synced_at": self.last_synced_at,
            "error": self.last_error if self.status == "error" else None,
        }
        if self.completion:
            health.update(
                {
                    "current_message_id": self.completion.current_message_id,
                    "processed_messages": self.completion.processed_messages,
                    "last_progress_at": self.completion.last_progress_at,
                }
            )
        return health

    async def _run(self) -> None:
        try:
            config = load_config()
            self.client = create_client(config)
            await start_client(self.client, config)
            config.destination = await resolve_destination(
                self.client, config.destination
            )

            store = self._create_checkpoint_store(config)
            self.completion = CompletionManager(
                client=self.client,
                source_channels=config.source_channels,
                store=store,
                process_message=lambda message: process_message(
                    self.client, config, message
                ),
            )

            await self.completion.initialize()
            register_handlers(self.client, config, self.completion)

            self.status = "syncing"
            await self.completion.sync_all()
            self.last_synced_at = self._now()
            self.status = "ready"
            logger.info("Telegram bot is ready")

            await self.client.run_until_disconnected()
            if not self._stopping:
                raise RuntimeError("Telegram client disconnected")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.status = "error"
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.exception("Telegram runtime failed")
        finally:
            if self.client and self.client.is_connected():
                await self.client.disconnect()

    @staticmethod
    def _create_checkpoint_store(config: BotConfig):
        if config.supabase_url and config.supabase_key:
            logger.info("Using Supabase checkpoint storage")
            return SupabaseCheckpointStore(config.supabase_url, config.supabase_key)

        logger.info("Using local checkpoint storage")
        return FileCheckpointStore(config.checkpoint_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
