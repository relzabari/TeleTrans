import unittest

from app.formatter import (
    build_media_caption,
    build_message,
    build_original_message_url,
    split_message,
)


class FormatterTests(unittest.TestCase):
    def test_build_message_contains_source_and_translation(self):
        message = build_message(
            "مرحبا",
            "قناة المصدر",
            "ערוץ מקור",
            "שלום",
            source_username="source_channel",
            original_sent_at="18/08/2026 14:35",
            source_message_id=123,
        )

        self.assertIn("מקור: قناة المصدر - ערוץ מקור (@source_channel)", message)
        self.assertIn("שלום", message)
        self.assertNotIn("مرحبا", message)
        self.assertIn(
            "[לחץ כאן להודעה המקורית](https://t.me/source_channel/123)",
            message,
        )
        self.assertIn("זמן פרסום מקורי: 18/08/2026 14:35 (שעון ישראל)", message)
        self.assertNotIn("🇸🇦", message)

    def test_original_text_is_fallback_when_link_cannot_be_built(self):
        message = build_message("مرحبا", "قناة", "ערוץ", "שלום")

        self.assertIn("הודעה מקורית:\n\nمرحبا", message)

    def test_private_channel_link_is_built_for_members(self):
        self.assertEqual(
            "https://t.me/c/1234567890/42",
            build_original_message_url(None, 42, -1001234567890),
        )

    def test_media_caption_contains_only_source(self):
        self.assertEqual(
            "מקור: قناة المصدر - ערוץ מקור (@source_channel)",
            build_media_caption("قناة المصدر", "ערוץ מקור", "@source_channel"),
        )

    def test_source_username_is_optional(self):
        self.assertEqual(
            "מקור: قناة المصدر - ערוץ מקור",
            build_media_caption("قناة المصدر", "ערוץ מקור"),
        )

    def test_media_caption_includes_original_timestamp(self):
        self.assertEqual(
            "מקור: قناة - ערוץ (@channel)\n"
            "זמן פרסום מקורי: 18/08/2026 14:35 (שעון ישראל)",
            build_media_caption(
                "قناة", "ערוץ", "channel", "18/08/2026 14:35"
            ),
        )

    def test_split_message_rejects_invalid_limit_and_returns_short_text(self):
        with self.assertRaises(ValueError):
            split_message("text", limit=0)
        self.assertEqual(["short"], split_message("short", limit=10))

    def test_split_message_preserves_content_within_limit(self):
        text = "פסקה ראשונה\n\n" + ("מילה " * 30) + "סוף"

        chunks = split_message(text, limit=40)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 40 for chunk in chunks))
        self.assertEqual(" ".join(text.split()), " ".join(" ".join(chunks).split()))

    def test_split_message_hard_splits_long_word(self):
        chunks = split_message("א" * 25, limit=10)

        self.assertEqual(["א" * 10, "א" * 10, "א" * 5], chunks)


if __name__ == "__main__":
    unittest.main()
