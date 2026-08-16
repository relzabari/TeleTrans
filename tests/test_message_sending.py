import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.telegram_client import process_message


class MessageSendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_translation_retries_then_succeeds(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            raw_text="مرحبا",
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="قناة", username="channel")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=[RuntimeError("temporary"), "שלום", "ערוץ"],
            ) as translate,
            patch("app.telegram_client.asyncio.sleep", AsyncMock()) as sleep,
            patch("app.telegram_client.is_supported_media", return_value=False),
        ):
            await process_message(client, config, event)

        self.assertEqual(3, translate.call_count)
        sleep.assert_awaited_once_with(2)
        self.assertIn("שלום", client.send_message.await_args.args[1])

    async def test_message_translation_failure_sends_fallback_and_continues(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            id=602725,
            raw_text="مستوطنون يعربدون",
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="فلسطين بوست", username="PalpostN")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=RuntimeError("translation unavailable"),
            ) as translate,
            patch("app.telegram_client.asyncio.sleep", AsyncMock()),
            patch("app.telegram_client.is_supported_media", return_value=False),
        ):
            await process_message(client, config, event)

        self.assertEqual(3, translate.call_count)
        client.send_message.assert_awaited_once()
        fallback = client.send_message.await_args.args[1]
        self.assertIn("תרגום ההודעה נכשל", fallback)
        self.assertIn("مستوطنون يعربدون", fallback)
        self.assertIn("@PalpostN", fallback)

    async def test_source_title_translation_failure_does_not_block_message(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            raw_text="مرحبا",
            get_chat=AsyncMock(
                return_value=SimpleNamespace(
                    title="فلسطين بوست", username="PalpostN"
                )
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=[
                    "שלום",
                    RuntimeError("title translation failed"),
                    RuntimeError("title translation failed"),
                    RuntimeError("title translation failed"),
                ],
            ),
            patch("app.telegram_client.asyncio.sleep", AsyncMock()),
            patch("app.telegram_client.is_supported_media", return_value=False),
        ):
            await process_message(client, config, event)

        client.send_message.assert_awaited_once()
        sent_message = client.send_message.await_args.args[1]
        self.assertIn(
            "מקור: فلسطين بوست - فلسطين بوست (@PalpostN)", sent_message
        )
        self.assertIn("שלום", sent_message)

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
