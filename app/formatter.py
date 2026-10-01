MEDIA_CAPTION_LIMIT = 1024
TEXT_MESSAGE_LIMIT = 4096


def build_important_message(message: str, matched_keywords: list[str]) -> str:
    matches = ", ".join(matched_keywords)
    return f"🚨 מילות מפתח שזוהו: {matches}\n\n{message}"


def build_message(
    original_text: str,
    source_title: str,
    translated_source_title: str,
    translated_text: str,
    source_username: str | None = None,
    original_sent_at: str | None = None,
    source_message_id: int | None = None,
    source_chat_id: int | None = None,
) -> str:
    timestamp = (
        f"\nזמן פרסום מקורי: {original_sent_at} (שעון ישראל)"
        if original_sent_at
        else ""
    )
    original_url = build_original_message_url(
        source_username, source_message_id, source_chat_id
    )
    original_reference = (
        f"[לחץ כאן להודעה המקורית]({original_url})"
        if original_url
        else f"הודעה מקורית:\n\n{original_text}"
    )
    return (
        f"{build_source_header(source_title, translated_source_title, source_username)}"
        f"{timestamp}\n\n"
        f"{translated_text}\n\n"
        f"────────────────────\n\n"
        f"{original_reference}"
    )


def build_original_message_url(
    source_username: str | None,
    source_message_id: int | None,
    source_chat_id: int | None = None,
) -> str | None:
    if source_message_id is None:
        return None

    username = source_username.strip().lstrip("@") if source_username else ""
    if username:
        return f"https://t.me/{username}/{source_message_id}"

    if source_chat_id is None:
        return None

    internal_chat_id = str(source_chat_id)
    if internal_chat_id.startswith("-100"):
        internal_chat_id = internal_chat_id[4:]
    elif internal_chat_id.startswith("-"):
        internal_chat_id = internal_chat_id[1:]
    if not internal_chat_id:
        return None
    return f"https://t.me/c/{internal_chat_id}/{source_message_id}"


def build_media_caption(
    source_title: str,
    translated_source_title: str,
    source_username: str | None = None,
    original_sent_at: str | None = None,
) -> str:
    header = build_source_header(
        source_title, translated_source_title, source_username
    )
    if original_sent_at:
        return f"{header}\nזמן פרסום מקורי: {original_sent_at} (שעון ישראל)"
    return header


def build_source_header(
    source_title: str,
    translated_source_title: str,
    source_username: str | None = None,
) -> str:
    username = source_username.strip().lstrip("@") if source_username else ""
    username_suffix = f" (@{username})" if username else ""
    return f"מקור: {source_title} - {translated_source_title}{username_suffix}"


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
