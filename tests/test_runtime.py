import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.config import BotConfig
from app.dynamic_config import DynamicConfig
from app.runtime import BotRuntime


def make_config(**overrides):
    values = {
        "source_channels": ["source"],
        "destination": "destination",
        "api_id": 1,
        "api_hash": "hash",
        "phone": "phone",
        "telegram_session": "session",
        "session_path": Path("session"),
        "checkpoint_path": Path("checkpoints.json"),
        "supabase_url": None,
        "supabase_key": None,
        "important_destination": None,
        "important_keywords": [],
    }
    values.update(overrides)
    return BotConfig(**values)


class FakeClient:
    def __init__(self, on_run=None, connected=True):
        self.on_run = on_run
        self.connected = connected
        self.disconnect = AsyncMock(side_effect=self._disconnect)

    def is_connected(self):
        return self.connected

    async def _disconnect(self):
        self.connected = False

    async def run_until_disconnected(self):
        if self.on_run:
            self.on_run()


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_idempotent_and_stop_disconnects_and_cancels(self):
        runtime = BotRuntime()
        blocker = asyncio.Event()

        async def running():
            await blocker.wait()

        with patch.object(runtime, "_run", side_effect=running) as run:
            runtime.start()
            first_task = runtime.task
            runtime.start()
            self.assertIs(first_task, runtime.task)
            self.assertEqual("starting", runtime.status)
            await runtime.stop()

        run.assert_called_once()
        self.assertEqual("stopped", runtime.status)

    async def test_stop_disconnects_connected_client(self):
        runtime = BotRuntime()
        runtime.client = FakeClient()
        await runtime.stop()
        runtime.client.disconnect.assert_awaited_once()

    async def test_wait_awaits_task_and_raises_for_error_status(self):
        runtime = BotRuntime()
        runtime.task = asyncio.create_task(asyncio.sleep(0))
        await runtime.wait()

        runtime.status = "error"
        runtime.last_error = "failure"
        with self.assertRaisesRegex(RuntimeError, "failure"):
            await runtime.wait()

        runtime.last_error = None
        with self.assertRaisesRegex(RuntimeError, "Telegram runtime failed"):
            await runtime.wait()

    def test_health_includes_completion_details_only_when_available(self):
        runtime = BotRuntime()
        self.assertNotIn("channels", runtime.health())

        runtime.status = "error"
        runtime.last_error = "failure"
        runtime.completion = SimpleNamespace(
            current_message_id=12,
            processed_messages=3,
            last_progress_at="now",
            health_channels=MagicMock(return_value={"source": {"state": "ready"}}),
        )
        health = runtime.health()
        self.assertEqual("failure", health["error"])
        self.assertEqual(12, health["current_message_id"])
        self.assertEqual(3, health["processed_messages"])
        self.assertIn("source", health["channels"])

    def test_checkpoint_store_selection(self):
        local_config = make_config()
        with patch("app.runtime.FileCheckpointStore") as local_store:
            self.assertIs(
                local_store.return_value,
                BotRuntime._create_checkpoint_store(local_config),
            )
            local_store.assert_called_once_with(local_config.checkpoint_path)

        remote_config = make_config(supabase_url="url", supabase_key="key")
        with patch("app.runtime.SupabaseCheckpointStore") as remote_store:
            self.assertIs(
                remote_store.return_value,
                BotRuntime._create_checkpoint_store(remote_config),
            )
            remote_store.assert_called_once_with("url", "key")

    def test_dynamic_config_store_selection_and_value_application(self):
        self.assertIsNone(BotRuntime._create_config_store(make_config()))
        remote_config = make_config(supabase_url="url", supabase_key="key")
        with patch("app.runtime.SupabaseConfigStore") as store:
            self.assertIs(
                store.return_value,
                BotRuntime._create_config_store(remote_config),
            )
            store.assert_called_once_with("url", "key")

        dynamic = DynamicConfig(
            source_channels=["new"],
            destination="new destination",
            important_destination="important",
            important_keywords=["keyword"],
            backfill_days=4,
            refresh_seconds=90,
        )
        BotRuntime._apply_dynamic_values(remote_config, dynamic)
        self.assertEqual(["new"], remote_config.source_channels)
        self.assertEqual("new destination", remote_config.destination)
        self.assertEqual("important", remote_config.important_destination)
        self.assertEqual(["keyword"], remote_config.important_keywords)
        self.assertEqual(4, remote_config.backfill_days)

    async def test_refresh_applies_changed_configuration(self):
        runtime = BotRuntime()
        runtime.client = object()
        runtime.completion = SimpleNamespace(
            update_source_channels=AsyncMock(), backfill_days=2
        )
        config = make_config(destination="resolved old")
        dynamic = DynamicConfig(
            source_channels=["new"],
            destination="new destination",
            important_destination="important",
            important_keywords=["keyword"],
            backfill_days=4,
            refresh_seconds=90,
        )
        store = SimpleNamespace(load=AsyncMock(return_value=dynamic))

        with (
            patch(
                "app.runtime.asyncio.sleep",
                AsyncMock(side_effect=[None, asyncio.CancelledError]),
            ),
            patch(
                "app.runtime.resolve_destination",
                AsyncMock(side_effect=["resolved new", "resolved important"]),
            ),
            patch.object(runtime, "_now", return_value="refreshed"),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await runtime._refresh_configuration_loop(
                    store, config, "old destination", None, 60
                )

        runtime.completion.update_source_channels.assert_awaited_once_with(["new"])
        self.assertEqual("resolved new", config.destination)
        self.assertEqual("resolved important", config.important_destination)
        self.assertEqual(["keyword"], config.important_keywords)
        self.assertEqual(4, runtime.completion.backfill_days)
        self.assertEqual("supabase", runtime.configuration_source)
        self.assertEqual("refreshed", runtime.config_last_refreshed_at)
        self.assertIsNone(runtime.config_error)

    async def test_run_completes_initialization_and_resolves_both_destinations(self):
        runtime = BotRuntime()
        config = make_config(important_destination="important")
        client = FakeClient(on_run=lambda: setattr(runtime, "_stopping", True))
        completion = MagicMock()
        completion.initialize = AsyncMock()
        completion.sync_all = AsyncMock()
        completion.current_message_id = None
        completion.processed_messages = 0
        completion.last_progress_at = None
        completion.health_channels.return_value = {}

        with (
            patch("app.runtime.load_config", return_value=config),
            patch("app.runtime.create_client", return_value=client),
            patch("app.runtime.start_client", AsyncMock()) as start_client,
            patch(
                "app.runtime.resolve_destination",
                AsyncMock(side_effect=["resolved-normal", "resolved-important"]),
            ) as resolve,
            patch.object(runtime, "_create_checkpoint_store", return_value="store"),
            patch("app.runtime.CompletionManager", return_value=completion) as manager,
            patch("app.runtime.register_handlers") as register,
            patch.object(runtime, "_now", return_value="synced"),
        ):
            await runtime._run()

        start_client.assert_awaited_once_with(client, config)
        self.assertEqual(2, resolve.await_count)
        manager.assert_called_once()
        completion.initialize.assert_awaited_once()
        completion.sync_all.assert_awaited_once()
        register.assert_called_once_with(client, config, completion)
        self.assertEqual("ready", runtime.status)
        self.assertEqual("synced", runtime.last_synced_at)
        client.disconnect.assert_awaited_once()

    async def test_run_without_important_destination_marks_disconnect_as_error(self):
        runtime = BotRuntime()
        config = make_config()
        client = FakeClient()
        completion = MagicMock(
            initialize=AsyncMock(),
            sync_all=AsyncMock(),
        )

        with (
            patch("app.runtime.load_config", return_value=config),
            patch("app.runtime.create_client", return_value=client),
            patch("app.runtime.start_client", AsyncMock()),
            patch("app.runtime.resolve_destination", AsyncMock(return_value="resolved")),
            patch.object(runtime, "_create_checkpoint_store", return_value="store"),
            patch("app.runtime.CompletionManager", return_value=completion),
            patch("app.runtime.register_handlers"),
        ):
            await runtime._run()

        self.assertEqual("error", runtime.status)
        self.assertIn("Telegram client disconnected", runtime.last_error)
        client.disconnect.assert_awaited_once()

    async def test_run_records_startup_error_without_client(self):
        runtime = BotRuntime()
        with patch("app.runtime.load_config", side_effect=ValueError("bad config")):
            await runtime._run()

        self.assertEqual("error", runtime.status)
        self.assertEqual("ValueError: bad config", runtime.last_error)

    async def test_run_propagates_cancellation(self):
        runtime = BotRuntime()
        with patch("app.runtime.load_config", side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await runtime._run()


if __name__ == "__main__":
    unittest.main()
