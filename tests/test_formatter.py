import unittest

from app.formatter import build_media_caption, build_message, split_message


class FormatterTests(unittest.TestCase):
    def test_build_message_contains_source_and_translation(self):
        message = build_message(
            "مرحبا",
            "قناة المصدر",
            "ערוץ מקור",
            "שלום",
            source_username="source_channel",
        )

        self.assertIn("מקור: قناة المصدر - ערוץ מקור (@source_channel)", message)
        self.assertIn("שלום", message)
        self.assertIn("مرحبا", message)
        self.assertIn("הודעה מקורית:", message)
        self.assertNotIn("🇸🇦", message)

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
