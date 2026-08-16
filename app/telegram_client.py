from __future__ import annotations

import asyncio
import logging
from typing import Any

from telethon import TelegramClient, events
from telethon.sessions import StringSession

from app.config import BotConfig
from app.completion import CompletionManager
from app.formatter import (
    MEDIA_CAPTION_LIMIT,
    build_media_caption,
    build_message,
    split_message,
)
from app.media import cleanup_file, download_media, is_supported_media
from app.translator import is_arabic_text, translate_to_hebrew

logger = logging.getLogger(__name__)

TRANSLATION_TIMEOUT_SECONDS = 60
TRANSLATION_ATTEMPTS = 3
TRANSLATION_RETRY_DELAY_SECONDS = 2
MEDIA_TIMEOUT_SECONDS = 120
SEND_TIMEOUT_SECONDS = 120


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
                f"הודעה מקורית:\n\n{text}"
            )
            await send_text_chunks(client, config.destination, fallback)
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
        )

        if is_supported_media(event):
            path = None
            try:
                path = await asyncio.wait_for(
                    download_media(event), timeout=MEDIA_TIMEOUT_SECONDS
                )
                if len(message) <= MEDIA_CAPTION_LIMIT:
                    await asyncio.wait_for(
                        client.send_file(config.destination, path, caption=message),
                        timeout=SEND_TIMEOUT_SECONDS,
                    )
                else:
                    await asyncio.wait_for(
                        client.send_file(
                            config.destination,
                            path,
                            caption=build_media_caption(
                                title,
                                translated_title,
                                source_username=username,
                            ),
                        ),
                        timeout=SEND_TIMEOUT_SECONDS,
                    )
                    await send_text_chunks(client, config.destination, message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Media unavailable for message %s (%s); sending text fallback",
                    getattr(event, "id", "unknown"),
                    type(exc).__name__,
                )
                fallback = f"⚠️ המדיה לא צורפה עקב שגיאת הורדה או שליחה.\n\n{message}"
                await send_text_chunks(client, config.destination, fallback)
            finally:
                cleanup_file(path)
        else:
            await send_text_chunks(client, config.destination, message)


async def translate_with_retry(text: str, purpose: str) -> str:
    last_error: Exception | None = None
    for attempt in range(1, TRANSLATION_ATTEMPTS + 1):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(translate_to_hebrew, text),
                timeout=TRANSLATION_TIMEOUT_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == TRANSLATION_ATTEMPTS:
                break
            logger.warning(
                "Could not translate %s on attempt %s/%s (%s); retrying",
                purpose,
                attempt,
                TRANSLATION_ATTEMPTS,
                type(exc).__name__,
            )
            await asyncio.sleep(TRANSLATION_RETRY_DELAY_SECONDS)

    assert last_error is not None
    raise last_error


async def send_text_chunks(client: TelegramClient, destination: Any, text: str) -> None:
    for chunk in split_message(text):
        await asyncio.wait_for(
            client.send_message(destination, chunk), timeout=SEND_TIMEOUT_SECONDS
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
