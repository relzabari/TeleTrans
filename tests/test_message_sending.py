import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.telegram_client import process_message


class MessageSendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_media_message_uses_short_caption_and_text_chunks(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            raw_text="ا" * 1200,
            get_chat=AsyncMock(return_value=SimpleNamespace(title="מקור")),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch("app.telegram_client.translate_to_hebrew", return_value="ת" * 1200),
            patch("app.telegram_client.is_supported_media", return_value=True),
            patch("app.telegram_client.download_media", AsyncMock(return_value="media.jpg")),
            patch("app.telegram_client.cleanup_file") as cleanup,
        ):
            await process_message(client, config, event)

        client.send_file.assert_awaited_once_with(
            "destination", "media.jpg", caption="מקור: מקור"
        )
        self.assertGreaterEqual(client.send_message.await_count, 1)
        self.assertTrue(
            all(len(call.args[1]) <= 4096 for call in client.send_message.await_args_list)
        )
        cleanup.assert_called_once_with("media.jpg")


if __name__ == "__main__":
    unittest.main()
