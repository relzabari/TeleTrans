import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.checkpoints import FileCheckpointStore
from app.completion import CompletionManager


class FakeTelegramClient:
    def __init__(self, message_ids):
        self.entity = SimpleNamespace(id=123)
        self.message_ids = list(message_ids)

    async def get_entity(self, source):
        return self.entity

    async def get_messages(self, entity, limit):
        if not self.message_ids:
            return []
        return [SimpleNamespace(id=max(self.message_ids))]

    async def iter_messages(self, entity, min_id, reverse):
        assert reverse is True
        for message_id in sorted(value for value in self.message_ids if value > min_id):
            yield SimpleNamespace(id=message_id)


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.store = FileCheckpointStore(
            Path(self.temporary_directory.name) / "checkpoints.json"
        )

    async def asyncTearDown(self):
        self.temporary_directory.cleanup()

    async def test_first_run_starts_at_latest_message_without_processing_history(self):
        processed = []
        client = FakeTelegramClient([1, 2, 3])
        manager = CompletionManager(
            client,
            ["source"],
            self.store,
            lambda message: self._record(processed, message),
            chat_id_resolver=lambda entity: -1000000000123,
        )

        await manager.initialize()
        count = await manager.sync_channel("source")

        self.assertEqual(0, count)
        self.assertEqual([], processed)
        self.assertEqual(3, await self.store.get(-1000000000123))

    async def test_sync_processes_only_missing_messages_in_order(self):
        processed = []
        client = FakeTelegramClient([3, 4, 5, 6])
        await self.store.set(-1000000000123, "source", 3)
        manager = CompletionManager(
            client,
            ["source"],
            self.store,
            lambda message: self._record(processed, message),
            chat_id_resolver=lambda entity: -1000000000123,
        )

        count = await manager.sync_channel("source")

        self.assertEqual(3, count)
        self.assertEqual([4, 5, 6], processed)
        self.assertEqual(6, await self.store.get(-1000000000123))
        self.assertEqual(3, manager.processed_messages)
        self.assertIsNotNone(manager.last_progress_at)
        self.assertIsNone(manager.current_message_id)

    async def test_failed_message_is_retried_without_skipping_following_messages(self):
        processed = []
        client = FakeTelegramClient([4, 5, 6])
        await self.store.set(-1000000000123, "source", 3)

        async def fail_on_five(message):
            if message.id == 5:
                raise RuntimeError("translation failed")
            processed.append(message.id)

        manager = CompletionManager(
            client,
            ["source"],
            self.store,
            fail_on_five,
            chat_id_resolver=lambda entity: -1000000000123,
        )

        with self.assertRaises(RuntimeError):
            await manager.sync_channel("source")

        self.assertEqual([4], processed)
        self.assertEqual(4, await self.store.get(-1000000000123))
        self.assertEqual(5, manager.current_message_id)

    @staticmethod
    async def _record(processed, message):
        processed.append(message.id)


if __name__ == "__main__":
    unittest.main()
