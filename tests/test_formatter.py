import unittest

from app.formatter import build_message


class FormatterTests(unittest.TestCase):
    def test_build_message_contains_source_and_translation(self):
        message = build_message("مرحبا", "ערוץ מקור", "שלום")

        self.assertIn("מקור: ערוץ מקור", message)
        self.assertIn("שלום", message)
        self.assertIn("مرحبا", message)


if __name__ == "__main__":
    unittest.main()
