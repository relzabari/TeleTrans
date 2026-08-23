from telethon.tl.types import MessageMediaDocument, MessageMediaPhoto


def is_supported_media(event) -> bool:
    return isinstance(getattr(event, "media", None), (MessageMediaPhoto, MessageMediaDocument))
