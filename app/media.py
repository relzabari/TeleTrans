import os
from typing import Optional

from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


def is_supported_media(event) -> bool:
    return isinstance(getattr(event, "media", None), (MessageMediaPhoto, MessageMediaDocument))


async def download_media(event) -> Optional[str]:
    if not is_supported_media(event):
        return None
    return await event.download_media()


def cleanup_file(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        os.remove(path)
