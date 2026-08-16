from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable


def normalize_for_matching(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).casefold()
    without_marks = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character) and character != "ـ"
    )
    return re.sub(r"\s+", " ", without_marks).strip()


def find_matching_keywords(
    original_text: str,
    translated_text: str,
    keywords: Iterable[str],
) -> list[str]:
    searchable = (
        normalize_for_matching(original_text),
        normalize_for_matching(translated_text),
    )
    matches: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        clean_keyword = str(keyword).strip()
        normalized_keyword = normalize_for_matching(clean_keyword)
        if not normalized_keyword or normalized_keyword in seen:
            continue
        if any(normalized_keyword in text for text in searchable):
            matches.append(clean_keyword)
            seen.add(normalized_keyword)

    return matches
