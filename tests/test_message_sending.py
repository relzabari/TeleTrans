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
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="מקור", username="source_channel")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=["ת" * 1200, "מקור מתורגם"],
            ),
            patch("app.telegram_client.is_supported_media", return_value=True),
            patch("app.telegram_client.download_media", AsyncMock(return_value="media.jpg")),
            patch("app.telegram_client.cleanup_file") as cleanup,
        ):
            await process_message(client, config, event)

        client.send_file.assert_awaited_once_with(
            "destination",
            "media.jpg",
            caption="מקור: מקור - מקור מתורגם (@source_channel)",
        )
        self.assertGreaterEqual(client.send_message.await_count, 1)
        self.assertTrue(
            all(len(call.args[1]) <= 4096 for call in client.send_message.await_args_list)
        )
        cleanup.assert_called_once_with("media.jpg")

    async def test_media_failure_sends_text_fallback(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            id=42,
            raw_text="مرحبا",
            get_chat=AsyncMock(return_value=SimpleNamespace(title="מקור")),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch("app.telegram_client.translate_to_hebrew", return_value="שלום"),
            patch("app.telegram_client.is_supported_media", return_value=True),
            patch(
                "app.telegram_client.download_media",
                AsyncMock(side_effect=TimeoutError),
            ),
            patch("app.telegram_client.cleanup_file") as cleanup,
        ):
            await process_message(client, config, event)

        client.send_file.assert_not_awaited()
        client.send_message.assert_awaited_once()
        self.assertIn("המדיה לא צורפה", client.send_message.await_args.args[1])
        cleanup.assert_called_once_with(None)


if __name__ == "__main__":
    unittest.main()
