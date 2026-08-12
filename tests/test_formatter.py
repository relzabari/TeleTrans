import unittest

from app.formatter import build_media_caption, build_message, split_message


class FormatterTests(unittest.TestCase):
    def test_build_message_contains_source_and_translation(self):
        message = build_message("مرحبا", "ערוץ מקור", "שלום")

        self.assertIn("מקור: ערוץ מקור", message)
        self.assertIn("שלום", message)
        self.assertIn("مرحبا", message)

    def test_media_caption_contains_only_source(self):
        self.assertEqual("מקור: ערוץ מקור", build_media_caption("ערוץ מקור"))

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
