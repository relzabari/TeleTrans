from __future__ import annotations

import logging

from app.config import load_config
from app.telegram_client import create_client, register_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main() -> None:
    config = load_config()
    client = create_client(config)
    register_handlers(client, config)

    logging.info("Starting Telegram translator bot...")
    await client.start(phone=config.phone)
    logging.info("Bot is running")
    await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
