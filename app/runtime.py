from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

from app.checkpoints import FileCheckpointStore, SupabaseCheckpointStore
from app.completion import CompletionManager
from app.config import BotConfig, load_config
from app.dynamic_config import DynamicConfig, SupabaseConfigStore
from app.telegram_client import (
    create_client,
    process_message,
    register_handlers,
    resolve_destination,
    start_client,
)
from app.time_utils import israel_now

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
        self.configuration_source = "file"
        self.config_last_refreshed_at: str | None = None
        self.config_error: str | None = None

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

    def health(self) -> dict[str, Any]:
        health: dict[str, Any] = {
            "status": self.status,
            "started_at": self.started_at,
            "last_synced_at": self.last_synced_at,
            "error": self.last_error if self.status == "error" else None,
            "configuration_source": self.configuration_source,
            "config_last_refreshed_at": self.config_last_refreshed_at,
            "config_error": self.config_error,
        }
        if self.completion:
            health.update(
                {
                    "current_message_id": self.completion.current_message_id,
                    "processed_messages": self.completion.processed_messages,
                    "last_progress_at": self.completion.last_progress_at,
                    "channels": self.completion.health_channels(),
                }
            )
        return health

    async def _run(self) -> None:
        try:
            config = load_config()
            config_store = self._create_config_store(config)
            dynamic_config: DynamicConfig | None = None
            if config_store:
                try:
                    dynamic_config = await config_store.load()
                    self._apply_dynamic_values(config, dynamic_config)
                    self.configuration_source = "supabase"
                    self.config_last_refreshed_at = self._now()
                    self.config_error = None
                    logger.info("Loaded dynamic configuration from Supabase")
                except Exception as exc:
                    self.configuration_source = "file"
                    self.config_error = f"{type(exc).__name__}: {exc}"
                    logger.exception(
                        "Could not load Supabase configuration; using config file"
                    )

            self.client = create_client(config)
            await start_client(self.client, config)
            destination_name = config.destination
            important_destination_name = config.important_destination
            config.destination = await resolve_destination(
                self.client, destination_name
            )
            if important_destination_name:
                config.important_destination = await resolve_destination(
                    self.client, important_destination_name
                )

            store = self._create_checkpoint_store(config)
            self.completion = CompletionManager(
                client=self.client,
                source_channels=config.source_channels,
                store=store,
                process_message=lambda message: process_message(
                    self.client, config, message
                ),
                backfill_days=config.backfill_days,
            )

            await self.completion.initialize()
            register_handlers(self.client, config, self.completion)

            self.status = "syncing"
            await self.completion.sync_all()
            self.last_synced_at = self._now()
            self.status = "ready"
            logger.info("Telegram bot is ready")

            refresh_task = None
            if config_store:
                refresh_task = asyncio.create_task(
                    self._refresh_configuration_loop(
                        config_store,
                        config,
                        destination_name,
                        important_destination_name,
                        dynamic_config.refresh_seconds if dynamic_config else 60,
                    ),
                    name="configuration-refresh",
                )
            try:
                await self.client.run_until_disconnected()
            finally:
                if refresh_task:
                    refresh_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await refresh_task
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
    def _create_config_store(config: BotConfig):
        if config.supabase_url and config.supabase_key:
            return SupabaseConfigStore(config.supabase_url, config.supabase_key)
        return None

    @staticmethod
    def _apply_dynamic_values(config: BotConfig, dynamic: DynamicConfig) -> None:
        config.source_channels = dynamic.source_channels
        config.destination = dynamic.destination
        config.important_destination = dynamic.important_destination
        config.important_keywords = dynamic.important_keywords
        config.backfill_days = dynamic.backfill_days

    async def _refresh_configuration_loop(
        self,
        store: SupabaseConfigStore,
        config: BotConfig,
        destination_name: str | int,
        important_destination_name: str | int | None,
        refresh_seconds: int,
    ) -> None:
        while True:
            await asyncio.sleep(refresh_seconds)
            try:
                dynamic = await store.load()
                new_destination = config.destination
                if dynamic.destination != destination_name:
                    new_destination = await resolve_destination(
                        self.client, dynamic.destination
                    )

                new_important_destination = config.important_destination
                if dynamic.important_destination != important_destination_name:
                    new_important_destination = (
                        await resolve_destination(
                            self.client, dynamic.important_destination
                        )
                        if dynamic.important_destination
                        else None
                    )

                await self.completion.update_source_channels(
                    dynamic.source_channels
                )
                config.destination = new_destination
                config.important_destination = new_important_destination
                config.important_keywords = dynamic.important_keywords
                config.backfill_days = dynamic.backfill_days
                self.completion.backfill_days = dynamic.backfill_days
                destination_name = dynamic.destination
                important_destination_name = dynamic.important_destination
                refresh_seconds = dynamic.refresh_seconds
                self.configuration_source = "supabase"
                self.config_last_refreshed_at = self._now()
                self.config_error = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.config_error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "Could not refresh dynamic configuration; keeping last values"
                )

    @staticmethod
    def _now() -> str:
        return israel_now()
