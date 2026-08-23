import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import (
    _get_required_env,
    _resolve_config_path,
    _resolve_session_path,
    load_config,
    get_project_root,
)


class ConfigTests(unittest.TestCase):
    def test_project_root_contains_application(self):
        self.assertTrue((get_project_root() / "app").is_dir())

    def test_required_env_strips_value_and_rejects_missing_values(self):
        with patch.dict(os.environ, {"VALUE": "  hello  "}, clear=True):
            self.assertEqual("hello", _get_required_env("VALUE"))

        for value in (None, "   "):
            environment = {} if value is None else {"VALUE": value}
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(RuntimeError, "VALUE"):
                    _get_required_env("VALUE")

    def test_config_path_prefers_data_and_falls_back_to_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            root_config = root / "config.json"
            root_config.write_text("{}", encoding="utf-8")
            self.assertEqual(root_config, _resolve_config_path(root))

            data_config = root / "data" / "config.json"
            data_config.parent.mkdir()
            data_config.write_text("{}", encoding="utf-8")
            self.assertEqual(data_config, _resolve_config_path(root))

    def test_missing_config_file_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                _resolve_config_path(Path(temporary))

    def test_session_path_prefers_legacy_session_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected_default = root / "data" / "sessions" / "telegram"
            self.assertEqual(expected_default, _resolve_session_path(root))

            legacy_file = root / "session" / "session.session"
            legacy_file.parent.mkdir()
            legacy_file.write_text("session", encoding="utf-8")
            self.assertEqual(root / "session" / "session", _resolve_session_path(root))

    def test_load_config_reads_values_and_cleans_keywords(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "data" / "config.json"
            config_path.parent.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "source_channels": ["one", "two"],
                        "destination": "target",
                        "important_destination": "important",
                        "important_keywords": [" word ", "", "   ", 123],
                    }
                ),
                encoding="utf-8",
            )
            environment = {
                "API_ID": "123",
                "API_HASH": " hash ",
                "PHONE": " phone ",
                "TELEGRAM_SESSION": "session",
                "SUPABASE_URL": "url",
                "SUPABASE_KEY": "key",
            }
            with (
                patch("app.config.get_project_root", return_value=root),
                patch("app.config.load_dotenv") as load_dotenv,
                patch.dict(os.environ, environment, clear=True),
            ):
                config = load_config()

            load_dotenv.assert_called_once_with(root / ".env")
            self.assertEqual(["one", "two"], config.source_channels)
            self.assertEqual("target", config.destination)
            self.assertEqual(123, config.api_id)
            self.assertEqual("hash", config.api_hash)
            self.assertEqual("phone", config.phone)
            self.assertEqual("session", config.telegram_session)
            self.assertEqual("url", config.supabase_url)
            self.assertEqual("key", config.supabase_key)
            self.assertEqual("important", config.important_destination)
            self.assertEqual(["word", "123"], config.important_keywords)
            self.assertTrue(config.session_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
