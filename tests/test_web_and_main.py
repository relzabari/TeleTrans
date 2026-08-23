import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import main as main_module
from app import web


class WebAndMainTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_returns_200_or_503(self):
        with patch.object(web.runtime, "health", return_value={"status": "ready"}):
            web.runtime.status = "ready"
            response = await web.health()
        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ready"}, json.loads(response.body))

        with patch.object(web.runtime, "health", return_value={"status": "error"}):
            web.runtime.status = "error"
            response = await web.health()
        self.assertEqual(503, response.status_code)

    async def test_lifespan_starts_and_stops_runtime(self):
        with (
            patch.object(web.runtime, "start") as start,
            patch.object(web.runtime, "stop", AsyncMock()) as stop,
        ):
            async with web.lifespan(web.app):
                start.assert_called_once()
            stop.assert_awaited_once()

    async def test_main_starts_waits_and_always_stops_runtime(self):
        runtime = SimpleNamespace(
            start=MagicMock(),
            wait=AsyncMock(),
            stop=AsyncMock(),
        )
        with patch("app.main.BotRuntime", return_value=runtime):
            await main_module.main()
        runtime.start.assert_called_once()
        runtime.wait.assert_awaited_once()
        runtime.stop.assert_awaited_once()

        runtime.wait = AsyncMock(side_effect=RuntimeError("failed"))
        with patch("app.main.BotRuntime", return_value=runtime):
            with self.assertRaisesRegex(RuntimeError, "failed"):
                await main_module.main()
        self.assertEqual(2, runtime.stop.await_count)


if __name__ == "__main__":
    unittest.main()
