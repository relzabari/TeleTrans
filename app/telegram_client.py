from __future__ import annotations

import asyncio
import logging
from typing import Any
from weakref import WeakKeyDictionary

from deep_translator.exceptions import TooManyRequests
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from app.config import BotConfig
from app.completion import CompletionManager
from app.formatter import (
    MEDIA_CAPTION_LIMIT,
    build_important_message,
    build_media_caption,
    build_message,
    split_message,
)
from app.keywords import find_matching_keywords
from app.media import is_supported_media
from app.translator import is_arabic_text, translate_to_hebrew
from app.time_utils import format_israel_datetime

logger = logging.getLogger(__name__)

TRANSLATION_TIMEOUT_SECONDS = 60
TRANSLATION_ATTEMPTS = 3
RATE_LIMIT_RETRY_DELAY_SECONDS = 60
RATE_LIMIT_MAX_DELAY_SECONDS = 600
SEND_TIMEOUT_SECONDS = 120
SEND_DELAY_SECONDS = 1
_translation_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    WeakKeyDictionary()
)
_send_locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    WeakKeyDictionary()
)


def _get_translation_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _translation_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _translation_locks[loop] = lock
    return lock


def _get_send_lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _send_locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _send_locks[loop] = lock
    return lock


async def _send_with_flood_wait(send_operation: Any, purpose: str) -> Any:
    """Serialize Telegram sends and retry after Telegram-requested flood waits."""
    async with _get_send_lock():
        while True:
            try:
                result = await asyncio.wait_for(
                    send_operation(), timeout=SEND_TIMEOUT_SECONDS
                )
            except asyncio.CancelledError:
                raise
            except FloodWaitError as exc:
                delay = max(int(exc.seconds), 1)
                logger.warning(
                    "Telegram flood wait reached while sending %s; waiting %s "
                    "seconds before retry",
                    purpose,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            await asyncio.sleep(SEND_DELAY_SECONDS)
            return result


def create_client(config: BotConfig) -> TelegramClient:
    session = (
        StringSession(config.telegram_session)
        if config.telegram_session
        else str(config.session_path)
    )
    return TelegramClient(session, config.api_id, config.api_hash)


async def start_client(client: TelegramClient, config: BotConfig) -> None:
    if not config.telegram_session:
        await client.start(phone=config.phone)
        return

    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise RuntimeError(
            "TELEGRAM_SESSION is invalid or expired; generate a new StringSession"
        )


async def resolve_destination(client: TelegramClient, destination: str) -> Any:
    try:
        return await client.get_entity(destination)
    except ValueError:
        pass

    async for dialog in client.iter_dialogs():
        title = getattr(dialog, "name", None) or getattr(dialog.entity, "title", None)
        if title == destination:
            return dialog.entity

    raise RuntimeError(
        f"Destination '{destination}' was not found by username, ID, or dialog title"
    )


async def process_message(client: TelegramClient, config: BotConfig, event: Any) -> None:
    text = event.raw_text or ""
    if text and is_arabic_text(text):
        chat = await event.get_chat()
        title = getattr(chat, "title", "") or "Unknown"
        username = getattr(chat, "username", None)
        original_sent_at = format_israel_datetime(getattr(event, "date", None))
        try:
            translated = await translate_with_retry(text, "message")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Could not translate message %s after %s attempts (%s); "
                "sending untranslated fallback",
                getattr(event, "id", "unknown"),
                TRANSLATION_ATTEMPTS,
                type(exc).__name__,
            )
            username_suffix = f" (@{str(username).lstrip('@')})" if username else ""
            fallback = (
                "⚠️ תרגום ההודעה נכשל לאחר מספר ניסיונות.\n\n"
                f"מקור: {title}{username_suffix}\n\n"
                + (
                    f"זמן פרסום מקורי: {original_sent_at} (שעון ישראל)\n\n"
                    if original_sent_at
                    else ""
                )
                + f"הודעה מקורית:\n\n{text}"
            )
            await send_text_chunks(client, config.destination, fallback)
            matches = find_matching_keywords(
                text, "", getattr(config, "important_keywords", [])
            )
            important_destination = getattr(config, "important_destination", None)
            if matches and important_destination:
                await send_text_chunks(
                    client,
                    important_destination,
                    build_important_message(fallback, matches),
                )
            return
        try:
            translated_title = await translate_with_retry(title, "source title")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Could not translate source title %r (%s); using original title",
                title,
                type(exc).__name__,
            )
            translated_title = title
        message = build_message(
            text,
            title,
            translated_title,
            translated,
            source_username=username,
            original_sent_at=original_sent_at,
        )
        matches = find_matching_keywords(
            text, translated, getattr(config, "important_keywords", [])
        )
        important_destination = getattr(config, "important_destination", None)
        important_message = (
            build_important_message(message, matches)
            if matches and important_destination
            else None
        )

        if is_supported_media(event):
            source_caption = build_media_caption(
                title,
                translated_title,
                source_username=username,
                original_sent_at=original_sent_at,
            )
            await send_server_side_media_or_fallback(
                client,
                config.destination,
                event.media,
                message,
                source_caption,
                getattr(event, "id", "unknown"),
            )
            if important_message:
                await send_server_side_media_or_fallback(
                    client,
                    important_destination,
                    event.media,
                    important_message,
                    build_important_message(source_caption, matches),
                    getattr(event, "id", "unknown"),
                )
        else:
            await send_text_chunks(client, config.destination, message)
            if important_message:
                await send_text_chunks(client, important_destination, important_message)


async def send_server_side_media_or_fallback(
    client: TelegramClient,
    destination: Any,
    media: Any,
    message: str,
    short_caption: str,
    message_id: Any,
) -> None:
    try:
        await send_server_side_media_message(
            client, destination, media, message, short_caption
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "Server-side media copy unavailable for message %s to %s (%s); "
            "sending text fallback",
            message_id,
            destination,
            type(exc).__name__,
        )
        fallback = f"⚠️ המדיה לא הועתקה מטלגרם.\n\n{message}"
        await send_text_chunks(client, destination, fallback)


async def send_server_side_media_message(
    client: TelegramClient,
    destination: Any,
    media: Any,
    message: str,
    short_caption: str,
) -> None:
    if len(message) <= MEDIA_CAPTION_LIMIT:
        await _send_with_flood_wait(
            lambda: client.send_file(destination, media, caption=message),
            "media",
        )
        return

    await _send_with_flood_wait(
        lambda: client.send_file(destination, media, caption=short_caption),
        "media",
    )
    await send_text_chunks(client, destination, message)


async def translate_with_retry(text: str, purpose: str) -> str:
    async with _get_translation_lock():
        return await _translate_with_retry_locked(text, purpose)


async def _translate_with_retry_locked(text: str, purpose: str) -> str:
    last_error: Exception | None = None
    regular_failures = 0
    rate_limit_failures = 0
    while regular_failures < TRANSLATION_ATTEMPTS:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(translate_to_hebrew, text),
                timeout=TRANSLATION_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except TooManyRequests:
            rate_limit_failures += 1
            delay = min(
                RATE_LIMIT_RETRY_DELAY_SECONDS * (2 ** (rate_limit_failures - 1)),
                RATE_LIMIT_MAX_DELAY_SECONDS,
            )
            logger.warning(
                "Translation rate limit reached for %s; waiting %s seconds "
                "before retry %s",
                purpose,
                delay,
                rate_limit_failures + 1,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            last_error = exc
            regular_failures += 1
            if regular_failures == TRANSLATION_ATTEMPTS:
                break
            logger.warning(
                "Could not translate %s on attempt %s/%s (%s); retrying",
                purpose,
                regular_failures,
                TRANSLATION_ATTEMPTS,
                type(exc).__name__,
            )

    assert last_error is not None
    raise last_error


async def send_text_chunks(client: TelegramClient, destination: Any, text: str) -> None:
    for chunk in split_message(text):
        await _send_with_flood_wait(
            lambda chunk=chunk: client.send_message(destination, chunk),
            "message",
        )


def register_handlers(
    client: TelegramClient, config: BotConfig, completion: CompletionManager
) -> None:
    @client.on(events.NewMessage(chats=config.source_channels))
    async def handler(event: Any) -> None:
        try:
            chat = await event.get_chat()
            await completion.sync_channel(chat)
        except Exception as exc:
            logger.exception("Failed to process message: %s", exc)

    return None
