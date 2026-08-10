from deep_translator import GoogleTranslator
from langdetect import detect


def is_arabic_text(text: str) -> bool:
    try:
        return detect(text) == "ar"
    except Exception:
        return False


def translate_to_hebrew(text: str) -> str:
    return GoogleTranslator(source="ar", target="iw").translate(text)
