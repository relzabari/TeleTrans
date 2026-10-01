import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.dynamic_config import SupabaseConfigStore


class FakeQuery:
    def __init__(self, data):
        self.data = data

    def select(self, *_args):
        return self

    def eq(self, *_args):
        return self

    def order(self, *_args):
        return self

    def limit(self, *_args):
        return self

    def execute(self):
        return SimpleNamespace(data=self.data)


class DynamicConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_enabled_configuration_from_supabase(self):
        tables = {
            "source_channels": FakeQuery(
                [{"username": "@one"}, {"username": "two"}]
            ),
            "important_keywords": FakeQuery(
                [{"phrase": " keyword "}, {"phrase": "מילה"}]
            ),
            "app_settings": FakeQuery(
                [
                    {
                        "destination": " regular ",
                        "important_destination": " important ",
                        "backfill_days": 3,
                        "config_refresh_seconds": 90,
                    }
                ]
            ),
        }
        client = MagicMock()
        client.table.side_effect=lambda name: tables[name]

        with patch("supabase.create_client", return_value=client):
            config = await SupabaseConfigStore("url", "key").load()

        self.assertEqual(["one", "two"], config.source_channels)
        self.assertEqual("regular", config.destination)
        self.assertEqual("important", config.important_destination)
        self.assertEqual(["keyword", "מילה"], config.important_keywords)
        self.assertEqual(3, config.backfill_days)
        self.assertEqual(90, config.refresh_seconds)

    async def test_rejects_missing_settings_or_no_enabled_channels(self):
        client = MagicMock()
        responses = {
            "source_channels": FakeQuery([]),
            "important_keywords": FakeQuery([]),
            "app_settings": FakeQuery([]),
        }
        client.table.side_effect=lambda name: responses[name]

        with patch("supabase.create_client", return_value=client):
            store = SupabaseConfigStore("url", "key")
        with self.assertRaisesRegex(RuntimeError, "app_settings"):
            await store.load()

        responses["app_settings"] = FakeQuery(
            [
                {
                    "destination": "target",
                    "important_destination": None,
                    "backfill_days": 2,
                    "config_refresh_seconds": 60,
                }
            ]
        )
        with self.assertRaisesRegex(RuntimeError, "no enabled source channels"):
            await store.load()


if __name__ == "__main__":
    unittest.main()
