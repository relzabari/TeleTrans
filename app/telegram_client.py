from __future__ import annotations

import asyncio
import logging
from typing import Any

from telethon import TelegramClient, events

from app.config import BotConfig
from app.completion import CompletionManager
from app.formatter import build_message
from app.media import cleanup_file, download_media, is_supported_media
from app.translator import is_arabic_text, translate_to_hebrew

logger = logging.getLogger(__name__)


def create_client(config: BotConfig) -> TelegramClient:
    return TelegramClient(str(config.session_path), config.api_id, config.api_hash)


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
                await client.send_file(config.destination, path, caption=message)
            finally:
                cleanup_file(path)
        else:
            await client.send_message(config.destination, message)


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
