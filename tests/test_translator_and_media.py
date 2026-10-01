import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from deep_translator.exceptions import TooManyRequests
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
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.translator.GoogleTranslator", return_value=translator) as factory,
        ):
            self.assertEqual("שלום", translate_to_hebrew("مرحبا"))
        factory.assert_called_once_with(source="ar", target="iw")
        translator.translate.assert_called_once_with("مرحبا")

    def test_translate_uses_azure_with_global_resource(self):
        response = MagicMock(status_code=200)
        response.json.return_value = [{"translations": [{"text": "שלום"}]}]
        environment = {
            "TRANSLATION_PROVIDER": "azure",
            "AZURE_TRANSLATOR_KEY": "secret",
            "AZURE_TRANSLATOR_REGION": "global",
            "AZURE_TRANSLATOR_ENDPOINT": "https://api.example/",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("app.translator.requests.post", return_value=response) as post,
        ):
            self.assertEqual("שלום", translate_to_hebrew("مرحبا"))

        response.raise_for_status.assert_called_once()
        request = post.call_args
        self.assertEqual("https://api.example/translate", request.args[0])
        self.assertEqual(
            {"api-version": "3.0", "from": "ar", "to": "he"},
            request.kwargs["params"],
        )
        self.assertNotIn("Ocp-Apim-Subscription-Region", request.kwargs["headers"])

    def test_azure_rate_limit_uses_existing_retry_exception(self):
        response = MagicMock(status_code=429)
        environment = {
            "TRANSLATION_PROVIDER": "azure",
            "AZURE_TRANSLATOR_KEY": "secret",
            "AZURE_TRANSLATOR_REGION": "israelcentral",
            "AZURE_TRANSLATOR_ENDPOINT": "https://api.example",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("app.translator.requests.post", return_value=response) as post,
        ):
            with self.assertRaises(TooManyRequests):
                translate_to_hebrew("مرحبا")

        self.assertEqual(
            "israelcentral",
            post.call_args.kwargs["headers"]["Ocp-Apim-Subscription-Region"],
        )

    def test_azure_requires_settings_and_valid_response(self):
        with patch.dict(os.environ, {"TRANSLATION_PROVIDER": "azure"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "AZURE_TRANSLATOR_KEY"):
                translate_to_hebrew("مرحبا")

        response = MagicMock(status_code=200)
        response.json.return_value = []
        environment = {
            "TRANSLATION_PROVIDER": "azure",
            "AZURE_TRANSLATOR_KEY": "secret",
            "AZURE_TRANSLATOR_REGION": "global",
            "AZURE_TRANSLATOR_ENDPOINT": "https://api.example",
        }
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("app.translator.requests.post", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected response"):
                translate_to_hebrew("مرحبا")

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
