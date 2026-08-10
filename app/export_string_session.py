from __future__ import annotations

import sys

from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import load_config


def main() -> None:
    config = load_config()
    client = TelegramClient(str(config.session_path), config.api_id, config.api_hash)
    session_string = StringSession.save(client.session)
    if not session_string:
        raise RuntimeError(
            f"No authorized Telegram session was found at {config.session_path}.session"
        )

    print(
        "SECRET: copy the next line directly into Render as TELEGRAM_SESSION. "
        "Do not commit or share it.",
        file=sys.stderr,
    )
    print(session_string)


if __name__ == "__main__":
    main()
