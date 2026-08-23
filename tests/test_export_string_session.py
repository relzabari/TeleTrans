import io
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app import export_string_session


def config():
    return SimpleNamespace(
        api_id=123,
        api_hash="hash",
        phone="phone",
        session_path=Path("telegram-session"),
    )


class ExportStringSessionTests(unittest.TestCase):
    def test_print_secret_splits_warning_and_secret_streams(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            export_string_session._print_secret("secret")
        self.assertEqual("secret\n", stdout.getvalue())
        self.assertIn("Do not commit", stderr.getvalue())

    def test_new_session_starts_prints_and_disconnects(self):
        client = SimpleNamespace(
            start=MagicMock(),
            disconnect=MagicMock(),
            session=SimpleNamespace(save=MagicMock(return_value="new-secret")),
        )
        with (
            patch.object(sys, "argv", ["export", "--new"]),
            patch("app.export_string_session.load_config", return_value=config()),
            patch("app.export_string_session.StringSession", return_value="empty-session"),
            patch("app.export_string_session.TelegramClient", return_value=client) as factory,
            patch("app.export_string_session._print_secret") as print_secret,
        ):
            export_string_session.main()

        factory.assert_called_once_with("empty-session", 123, "hash")
        client.start.assert_called_once_with(phone="phone")
        print_secret.assert_called_once_with("new-secret")
        client.disconnect.assert_called_once()

    def test_new_session_disconnects_even_when_start_fails(self):
        client = SimpleNamespace(
            start=MagicMock(side_effect=RuntimeError("login failed")),
            disconnect=MagicMock(),
        )
        with (
            patch.object(sys, "argv", ["export", "--new"]),
            patch("app.export_string_session.load_config", return_value=config()),
            patch("app.export_string_session.StringSession", return_value="empty-session"),
            patch("app.export_string_session.TelegramClient", return_value=client),
        ):
            with self.assertRaisesRegex(RuntimeError, "login failed"):
                export_string_session.main()
        client.disconnect.assert_called_once()

    def test_existing_session_exports_or_rejects_missing_authorization(self):
        client = SimpleNamespace(session=object())
        with (
            patch.object(sys, "argv", ["export"]),
            patch("app.export_string_session.load_config", return_value=config()),
            patch("app.export_string_session.TelegramClient", return_value=client) as factory,
            patch("app.export_string_session.StringSession") as string_session,
            patch("app.export_string_session._print_secret") as print_secret,
        ):
            string_session.save.return_value = "existing-secret"
            export_string_session.main()

        factory.assert_called_once_with("telegram-session", 123, "hash")
        print_secret.assert_called_once_with("existing-secret")

        with (
            patch.object(sys, "argv", ["export"]),
            patch("app.export_string_session.load_config", return_value=config()),
            patch("app.export_string_session.TelegramClient", return_value=client),
            patch("app.export_string_session.StringSession") as string_session,
        ):
            string_session.save.return_value = ""
            with self.assertRaisesRegex(RuntimeError, "No authorized Telegram session"):
                export_string_session.main()


if __name__ == "__main__":
    unittest.main()
