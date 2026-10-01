import os

import requests
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TooManyRequests
from langdetect import detect

AZURE_TRANSLATION_API_VERSION = "3.0"
TRANSLATION_REQUEST_TIMEOUT_SECONDS = 60


def is_arabic_text(text: str) -> bool:
    try:
        return detect(text) == "ar"
    except Exception:
        return False


def translate_to_hebrew(text: str) -> str:
    provider = os.getenv("TRANSLATION_PROVIDER", "google").strip().lower()
    if provider == "azure":
        return _translate_with_azure(text)
    if provider != "google":
        raise RuntimeError(f"Unsupported translation provider: {provider}")
    return GoogleTranslator(source="ar", target="iw").translate(text)


def _translate_with_azure(text: str) -> str:
    key = _required_setting("AZURE_TRANSLATOR_KEY")
    endpoint = _required_setting("AZURE_TRANSLATOR_ENDPOINT").rstrip("/")
    region = _required_setting("AZURE_TRANSLATOR_REGION")
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "application/json",
    }
    if region.lower() != "global":
        headers["Ocp-Apim-Subscription-Region"] = region

    response = requests.post(
        f"{endpoint}/translate",
        params={"api-version": AZURE_TRANSLATION_API_VERSION, "from": "ar", "to": "he"},
        headers=headers,
        json=[{"text": text}],
        timeout=TRANSLATION_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code == 429:
        raise TooManyRequests()
    response.raise_for_status()
    try:
        return str(response.json()[0]["translations"][0]["text"])
    except (IndexError, KeyError, TypeError) as exc:
        raise RuntimeError("Azure Translator returned an unexpected response") from exc


def _required_setting(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing environment variable: {name}")
    return value.strip()
