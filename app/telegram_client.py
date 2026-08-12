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
        translated = await asyncio.to_thread(translate_to_hebrew, text)
        message = build_message(text, title, translated)

        if is_supported_media(event):
            path = await download_media(event)
            try:
                if len(message) <= MEDIA_CAPTION_LIMIT:
                    await client.send_file(config.destination, path, caption=message)
                else:
                    await client.send_file(
                        config.destination,
                        path,
                        caption=build_media_caption(title),
                    )
                    await send_text_chunks(client, config.destination, message)
            finally:
                cleanup_file(path)
        else:
            await send_text_chunks(client, config.destination, message)


async def send_text_chunks(client: TelegramClient, destination: Any, text: str) -> None:
    for chunk in split_message(text):
        await client.send_message(destination, chunk)


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
