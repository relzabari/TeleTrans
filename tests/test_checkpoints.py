import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.checkpoints import FileCheckpointStore, SupabaseCheckpointStore


class CheckpointStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_file_store_returns_none_then_persists_and_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "nested" / "checkpoints.json"
            store = FileCheckpointStore(path)

            self.assertIsNone(await store.get(123))
            await store.set(123, "source", 7)
            self.assertEqual(7, await store.get(123))
            await store.set(123, "source", 8)
            self.assertEqual(8, await store.get(123))
            self.assertFalse(path.with_suffix(".tmp").exists())

    async def test_supabase_store_gets_missing_and_existing_values_and_upserts(self):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.limit.return_value = query
        query.upsert.return_value = query
        query.execute.side_effect = [
            SimpleNamespace(data=[]),
            SimpleNamespace(data=[{"last_message_id": "42"}]),
            SimpleNamespace(data=[]),
        ]
        client = MagicMock()
        client.table.return_value = query

        with patch("supabase.create_client", return_value=client) as create_client:
            store = SupabaseCheckpointStore("url", "key")
            self.assertIsNone(await store.get(1))
            self.assertEqual(42, await store.get(1))
            await store.set(1, "source", 43)

        create_client.assert_called_once_with("url", "key")
        query.upsert.assert_called_once_with(
            {
                "source_chat_id": 1,
                "source_channel": "source",
                "last_message_id": 43,
            },
            on_conflict="source_chat_id",
        )


if __name__ == "__main__":
    unittest.main()
