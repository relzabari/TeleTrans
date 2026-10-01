import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from telethon.errors import FloodWaitError

from app.telegram_client import process_message, send_text_chunks


class MessageSendingTests(unittest.IsolatedAsyncioTestCase):
    async def test_flood_wait_sleeps_and_retries_same_message(self):
        flood_wait = FloodWaitError(request=None, capture=240)
        client = SimpleNamespace(
            send_message=AsyncMock(side_effect=[flood_wait, "sent"])
        )

        with patch("app.telegram_client.asyncio.sleep", AsyncMock()) as sleep:
            await send_text_chunks(client, "destination", "message")

        self.assertEqual(2, client.send_message.await_count)
        self.assertEqual(
            client.send_message.await_args_list[0],
            client.send_message.await_args_list[1],
        )
        self.assertEqual(240, sleep.await_args_list[0].args[0])

    async def test_non_flood_send_error_is_not_retried(self):
        client = SimpleNamespace(
            send_message=AsyncMock(side_effect=RuntimeError("send failed"))
        )

        with self.assertRaisesRegex(RuntimeError, "send failed"):
            await send_text_chunks(client, "destination", "message")

        client.send_message.assert_awaited_once()

    async def test_keyword_match_sends_message_to_both_destinations(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(
            destination="destination",
            important_destination="important",
            important_keywords=["صاروخ", "נריה"],
        )
        event = SimpleNamespace(
            raw_text="إطلاق صاروخ",
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="قناة", username="channel")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=["דיווח באזור נריה", "ערוץ"],
            ),
            patch("app.telegram_client.is_supported_media", return_value=False),
        ):
            await process_message(client, config, event)

        self.assertEqual(2, client.send_message.await_count)
        normal_call, important_call = client.send_message.await_args_list
        self.assertEqual("destination", normal_call.args[0])
        self.assertNotIn("🚨", normal_call.args[1])
        self.assertEqual("important", important_call.args[0])
        self.assertIn("🚨 מילות מפתח שזוהו: صاروخ, נריה", important_call.args[1])

    async def test_no_keyword_match_sends_only_to_normal_destination(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(
            destination="destination",
            important_destination="important",
            important_keywords=["פיגוע"],
        )
        event = SimpleNamespace(
            raw_text="خبر عادي",
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="قناة", username="channel")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=["דיווח רגיל", "ערוץ"],
            ),
            patch("app.telegram_client.is_supported_media", return_value=False),
        ):
            await process_message(client, config, event)

        client.send_message.assert_awaited_once()
        self.assertEqual("destination", client.send_message.await_args.args[0])

    async def test_keyword_media_is_copied_server_side_to_both_destinations(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(
            destination="destination",
            important_destination="important",
            important_keywords=["صاروخ"],
        )
        media = object()
        event = SimpleNamespace(
            raw_text="صاروخ",
            media=media,
            get_chat=AsyncMock(
                return_value=SimpleNamespace(title="قناة", username="channel")
            ),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch(
                "app.telegram_client.translate_to_hebrew",
                side_effect=["טיל", "ערוץ"],
            ),
            patch("app.telegram_client.is_supported_media", return_value=True),
        ):
            await process_message(client, config, event)

        self.assertEqual(2, client.send_file.await_count)
        self.assertEqual("destination", client.send_file.await_args_list[0].args[0])
        self.assertIs(media, client.send_file.await_args_list[0].args[1])
        self.assertEqual("important", client.send_file.await_args_list[1].args[0])
        self.assertIs(media, client.send_file.await_args_list[1].args[1])
        self.assertIn("🚨", client.send_file.await_args_list[1].kwargs["caption"])

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
        sleep.assert_awaited_once_with(1)
        self.assertIn("שלום", client.send_message.await_args.args[1])

    async def test_message_translation_failure_sends_fallback_and_continues(self):
        client = SimpleNamespace(send_file=AsyncMock(), send_message=AsyncMock())
        config = SimpleNamespace(
            destination="destination",
            important_destination="important",
            important_keywords=["Ù…Ø³ØªÙˆØ·Ù†ÙˆÙ†"],
        )
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
            patch("app.telegram_client.find_matching_keywords", return_value=["keyword"]),
        ):
            await process_message(client, config, event)

        self.assertEqual(3, translate.call_count)
        self.assertEqual(2, client.send_message.await_count)
        fallback = client.send_message.await_args_list[0].args[1]
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
        media = object()
        event = SimpleNamespace(
            raw_text="ا" * 1200,
            media=media,
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
        ):
            await process_message(client, config, event)

        client.send_file.assert_awaited_once_with(
            "destination",
            media,
            caption="מקור: מקור - מקור מתורגם (@source_channel)",
        )
        self.assertGreaterEqual(client.send_message.await_count, 1)
        self.assertTrue(
            all(len(call.args[1]) <= 4096 for call in client.send_message.await_args_list)
        )
        client.send_file.assert_awaited_once()

    async def test_media_failure_sends_text_fallback(self):
        client = SimpleNamespace(
            send_file=AsyncMock(side_effect=TimeoutError),
            send_message=AsyncMock(),
        )
        config = SimpleNamespace(destination="destination")
        event = SimpleNamespace(
            id=42,
            raw_text="مرحبا",
            media=object(),
            get_chat=AsyncMock(return_value=SimpleNamespace(title="מקור")),
        )

        with (
            patch("app.telegram_client.is_arabic_text", return_value=True),
            patch("app.telegram_client.translate_to_hebrew", return_value="שלום"),
            patch("app.telegram_client.is_supported_media", return_value=True),
        ):
            await process_message(client, config, event)

        client.send_file.assert_awaited_once()
        client.send_message.assert_awaited_once()
        self.assertIn("המדיה לא הועתקה", client.send_message.await_args.args[1])


if __name__ == "__main__":
    unittest.main()
