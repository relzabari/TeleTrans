from __future__ import annotations

import argparse
import sys

from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from app.config import load_config


def _print_secret(session_string: str) -> None:
    print(
        "SECRET: copy the next line directly into Render as TELEGRAM_SESSION. "
        "Do not commit or share it.",
        file=sys.stderr,
    )
    print(session_string)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a Telegram StringSession")
    parser.add_argument(
        "--new",
        action="store_true",
        help="create a fresh authorization instead of exporting the SQLite session",
    )
    args = parser.parse_args()
    config = load_config()

    if args.new:
        client = TelegramClient(StringSession(), config.api_id, config.api_hash)
        try:
            client.start(phone=config.phone)
            _print_secret(client.session.save())
        finally:
            client.disconnect()
        return

    client = TelegramClient(str(config.session_path), config.api_id, config.api_hash)
    session_string = StringSession.save(client.session)
    if not session_string:
        raise RuntimeError(
            f"No authorized Telegram session was found at {config.session_path}.session"
        )

    _print_secret(session_string)


if __name__ == "__main__":
    main()
