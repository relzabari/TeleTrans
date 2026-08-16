MEDIA_CAPTION_LIMIT = 1024
TEXT_MESSAGE_LIMIT = 4096


def build_message(
    original_text: str,
    source_title: str,
    translated_source_title: str,
    translated_text: str,
) -> str:
    return (
        f"מקור: {source_title} - {translated_source_title}\n\n"
        f"{translated_text}\n\n"
        f"────────────────────\n\n"
        f"הודעה מקורית:\n\n"
        f"{original_text}"
    )


def build_media_caption(source_title: str, translated_source_title: str) -> str:
    return f"מקור: {source_title} - {translated_source_title}"


def split_message(text: str, limit: int = TEXT_MESSAGE_LIMIT) -> list[str]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, limit + 1)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, limit + 1)
        if split_at <= 0:
            split_at = limit

        chunk = remaining[:split_at].rstrip()
        chunks.append(chunk or remaining[:limit])
        remaining = remaining[split_at:].lstrip()

    return chunks
