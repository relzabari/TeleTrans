from __future__ import annotations

import asyncio
import logging

from app.runtime import BotRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


async def main() -> None:
    runtime = BotRuntime()
    runtime.start()
    try:
        await runtime.wait()
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
