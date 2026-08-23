import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto

from app.media import is_supported_media
from app.translator import is_arabic_text, translate_to_hebrew


class TranslatorAndMediaTests(unittest.TestCase):
    def test_arabic_detection_handles_languages_and_errors(self):
        with patch("app.translator.detect", return_value="ar"):
            self.assertTrue(is_arabic_text("text"))
        with patch("app.translator.detect", return_value="he"):
            self.assertFalse(is_arabic_text("text"))
        with patch("app.translator.detect", side_effect=RuntimeError):
            self.assertFalse(is_arabic_text("text"))

    def test_translate_uses_arabic_to_hebrew_google_translator(self):
        translator = MagicMock()
        translator.translate.return_value = "שלום"
        with patch("app.translator.GoogleTranslator", return_value=translator) as factory:
            self.assertEqual("שלום", translate_to_hebrew("مرحبا"))
        factory.assert_called_once_with(source="ar", target="iw")
        translator.translate.assert_called_once_with("مرحبا")

    def test_supported_media_recognizes_photos_and_documents_only(self):
        self.assertTrue(
            is_supported_media(SimpleNamespace(media=MessageMediaPhoto(photo=None)))
        )
        self.assertTrue(
            is_supported_media(SimpleNamespace(media=MessageMediaDocument(document=None)))
        )
        self.assertFalse(is_supported_media(SimpleNamespace(media=None)))
        self.assertFalse(is_supported_media(SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
