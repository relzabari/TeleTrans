from __future__ import annotations

import logging

from app.checkpoints import FileCheckpointStore, SupabaseCheckpointStore
from app.completion import CompletionManager
from app.config import load_config
from app.telegram_client import create_client, process_message, register_handlers

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main() -> None:
    config = load_config()
    client = create_client(config)

    logging.info("Starting Telegram translator bot...")
    await client.start(phone=config.phone)

    if config.supabase_url and config.supabase_key:
        checkpoint_store = SupabaseCheckpointStore(
            config.supabase_url, config.supabase_key
        )
        logging.info("Using Supabase checkpoint storage")
    else:
        checkpoint_store = FileCheckpointStore(config.checkpoint_path)
        logging.info("Using local checkpoint storage")

    completion = CompletionManager(
        client=client,
        source_channels=config.source_channels,
        store=checkpoint_store,
        process_message=lambda message: process_message(client, config, message),
    )

    # Initialize first so a brand-new deployment does not translate all history.
    await completion.initialize()
    register_handlers(client, config, completion)
    # Close the small gap between initialization and handler registration.
    await completion.sync_all()

    logging.info("Bot is running")
    await client.run_until_disconnected()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
