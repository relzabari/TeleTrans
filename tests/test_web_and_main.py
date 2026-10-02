import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from app import main as main_module
from app import web


class WebAndMainTests(unittest.IsolatedAsyncioTestCase):
    def test_admin_authentication_requires_configuration_and_valid_credentials(self):
        credentials = HTTPBasicCredentials(username="admin", password="secret")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(HTTPException) as missing:
                web.require_admin(credentials)
        self.assertEqual(503, missing.exception.status_code)

        environment = {"ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": "secret"}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual("admin", web.require_admin(credentials))
            with self.assertRaises(HTTPException) as invalid:
                web.require_admin(
                    HTTPBasicCredentials(username="admin", password="wrong")
                )
        self.assertEqual(401, invalid.exception.status_code)

    async def test_admin_page_and_crud_endpoints_use_protected_store(self):
        store = SimpleNamespace(
            get_configuration=AsyncMock(
                return_value={"channels": [], "keywords": [], "settings": {}}
            ),
            insert=AsyncMock(return_value={"id": 1}),
            update=AsyncMock(return_value={"id": 1}),
            delete=AsyncMock(),
        )
        with (
            patch("app.web.get_admin_store", return_value=store),
            patch(
                "app.web._resolve_source_channel",
                AsyncMock(return_value=("channel", -100123)),
            ),
        ):
            page = await web.admin_page("admin")
            self.assertIn("TeleTrans", page.body.decode("utf-8"))
            self.assertEqual(
                {"channels": [], "keywords": [], "settings": {}},
                await web.admin_config("admin"),
            )
            await web.create_channel(
                web.ChannelCreate(username=" @channel ", display_name=" Name "),
                "admin",
            )
            await web.create_keyword(
                web.KeywordCreate(
                    phrase=" phrase ", language=" Arabic ", category=" Alert "
                ),
                "admin",
            )
            await web.update_settings(
                web.SettingsUpdate(backfill_days=3), "admin"
            )
            response = await web.delete_channel(1, "admin")

        store.insert.assert_any_await(
            "source_channels",
            {
                "username": "channel",
                "display_name": "Name",
                "source_chat_id": -100123,
            },
        )
        store.insert.assert_any_await(
            "important_keywords",
            {"phrase": "phrase", "language": "Arabic", "category": "Alert"},
        )
        store.update.assert_awaited_once_with(
            "app_settings", 1, {"backfill_days": 3}
        )
        store.delete.assert_awaited_once_with("source_channels", 1)
        self.assertEqual(204, response.status_code)

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
