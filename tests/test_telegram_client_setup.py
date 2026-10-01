import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from deep_translator.exceptions import TooManyRequests
from app.config import BotConfig
from app.telegram_client import (
    create_client,
    process_message,
    register_handlers,
    resolve_destination,
    send_server_side_media_or_fallback,
    start_client,
    translate_with_retry,
)


def make_config(session="session"):
    return BotConfig(
        source_channels=["one", "two"],
        destination="destination",
        api_id=123,
        api_hash="hash",
        phone="phone",
        telegram_session=session,
        session_path=Path("local-session"),
        checkpoint_path=Path("checkpoint"),
        supabase_url=None,
        supabase_key=None,
    )


class AsyncDialogs:
    def __init__(self, dialogs):
        self.dialogs = dialogs

    def __aiter__(self):
        async def iterate():
            for dialog in self.dialogs:
                yield dialog
        return iterate()


class TelegramClientSetupTests(unittest.IsolatedAsyncioTestCase):
    def test_create_client_uses_string_or_file_session(self):
        with (
            patch("app.telegram_client.StringSession", return_value="string-session") as string,
            patch("app.telegram_client.TelegramClient", return_value="client") as client,
        ):
            self.assertEqual("client", create_client(make_config("secret")))
            string.assert_called_once_with("secret")
            client.assert_called_once_with("string-session", 123, "hash")

        with patch("app.telegram_client.TelegramClient", return_value="client") as client:
            self.assertEqual("client", create_client(make_config(None)))
            client.assert_called_once_with("local-session", 123, "hash")

    async def test_start_client_supports_local_and_authorized_string_sessions(self):
        local_client = SimpleNamespace(start=AsyncMock())
        await start_client(local_client, make_config(None))
        local_client.start.assert_awaited_once_with(phone="phone")

        remote_client = SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=True),
        )
        await start_client(remote_client, make_config("secret"))
        remote_client.connect.assert_awaited_once()
        remote_client.disconnect.assert_not_awaited()

    async def test_invalid_string_session_disconnects_and_raises(self):
        client = SimpleNamespace(
            connect=AsyncMock(),
            disconnect=AsyncMock(),
            is_user_authorized=AsyncMock(return_value=False),
        )
        with self.assertRaisesRegex(RuntimeError, "invalid or expired"):
            await start_client(client, make_config("secret"))
        client.disconnect.assert_awaited_once()

    async def test_resolve_destination_direct_dialog_and_failure_paths(self):
        direct = SimpleNamespace(get_entity=AsyncMock(return_value="entity"))
        self.assertEqual("entity", await resolve_destination(direct, "target"))

        matching_entity = SimpleNamespace(title="Target")
        dialog_client = SimpleNamespace(
            get_entity=AsyncMock(side_effect=ValueError),
            iter_dialogs=MagicMock(
                return_value=AsyncDialogs(
                    [
                        SimpleNamespace(name="Other", entity=SimpleNamespace(title="Other")),
                        SimpleNamespace(name=None, entity=matching_entity),
                    ]
                )
            ),
        )
        self.assertIs(matching_entity, await resolve_destination(dialog_client, "Target"))

        missing = SimpleNamespace(
            get_entity=AsyncMock(side_effect=ValueError),
            iter_dialogs=MagicMock(return_value=AsyncDialogs([])),
        )
        with self.assertRaisesRegex(RuntimeError, "was not found"):
            await resolve_destination(missing, "Missing")

    async def test_process_message_ignores_empty_and_non_arabic_text(self):
        client = SimpleNamespace(send_message=AsyncMock())
        config = SimpleNamespace(destination="destination")
        for text, arabic in (("", True), ("hello", False)):
            event = SimpleNamespace(raw_text=text)
            with patch("app.telegram_client.is_arabic_text", return_value=arabic):
                await process_message(client, config, event)
        client.send_message.assert_not_awaited()

    async def test_process_message_propagates_translation_cancellations(self):
        event = SimpleNamespace(
            raw_text="arabic", date=None,
            get_chat=AsyncMock(return_value=SimpleNamespace(title="title")),
        )
        for side_effect in (
            asyncio.CancelledError(),
            ["translated", asyncio.CancelledError()],
        ):
            with (
                patch("app.telegram_client.is_arabic_text", return_value=True),
                patch(
                    "app.telegram_client.translate_with_retry",
                    AsyncMock(side_effect=side_effect),
                ),
            ):
                with self.assertRaises(asyncio.CancelledError):
                    await process_message(SimpleNamespace(), make_config(), event)

    async def test_translate_with_retry_propagates_cancellation(self):
        with patch(
            "app.telegram_client.asyncio.to_thread",
            side_effect=asyncio.CancelledError,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await translate_with_retry("text", "message")

    async def test_translate_with_retry_waits_only_for_rate_limits(self):
        with (
            patch(
                "app.telegram_client.asyncio.to_thread",
                AsyncMock(side_effect=[TooManyRequests(), TooManyRequests(), "translated"]),
            ),
            patch("app.telegram_client.asyncio.sleep", AsyncMock()) as sleep,
        ):
            result = await translate_with_retry("text", "message")

        self.assertEqual("translated", result)
        self.assertEqual([60, 120], [call.args[0] for call in sleep.await_args_list])

    async def test_translate_with_retry_does_not_give_up_on_rate_limits(self):
        rate_limits = [TooManyRequests() for _ in range(5)]
        with (
            patch(
                "app.telegram_client.asyncio.to_thread",
                AsyncMock(side_effect=[*rate_limits, "translated"]),
            ),
            patch("app.telegram_client.asyncio.sleep", AsyncMock()) as sleep,
        ):
            result = await translate_with_retry("text", "message")

        self.assertEqual("translated", result)
        self.assertEqual(
            [60, 120, 240, 480, 600],
            [call.args[0] for call in sleep.await_args_list],
        )

    async def test_translate_with_retry_does_not_wait_for_other_errors(self):
        with (
            patch(
                "app.telegram_client.asyncio.to_thread",
                AsyncMock(side_effect=[RuntimeError("temporary"), "translated"]),
            ),
            patch("app.telegram_client.asyncio.sleep", AsyncMock()) as sleep,
        ):
            result = await translate_with_retry("text", "message")

        self.assertEqual("translated", result)
        sleep.assert_not_awaited()

    async def test_translation_requests_are_serialized_globally(self):
        active_requests = 0
        maximum_active_requests = 0

        async def translate_in_thread(_function, text):
            nonlocal active_requests, maximum_active_requests
            active_requests += 1
            maximum_active_requests = max(maximum_active_requests, active_requests)
            await asyncio.sleep(0.01)
            active_requests -= 1
            return f"translated-{text}"

        with patch(
            "app.telegram_client.asyncio.to_thread",
            AsyncMock(side_effect=translate_in_thread),
        ):
            results = await asyncio.gather(
                translate_with_retry("one", "message"),
                translate_with_retry("two", "message"),
                translate_with_retry("three", "message"),
            )

        self.assertEqual(
            ["translated-one", "translated-two", "translated-three"], results
        )
        self.assertEqual(1, maximum_active_requests)

    async def test_media_copy_cancellation_is_not_swallowed(self):
        client = SimpleNamespace(send_file=AsyncMock(side_effect=asyncio.CancelledError))
        with self.assertRaises(asyncio.CancelledError):
            await send_server_side_media_or_fallback(
                client, "destination", object(), "message", "caption", 1
            )

    async def test_register_handler_syncs_chat_and_logs_handler_errors(self):
        callbacks = []
        client = SimpleNamespace(
            on=MagicMock(side_effect=lambda _event: lambda callback: callbacks.append(callback))
        )
        completion = SimpleNamespace(sync_channel=AsyncMock())
        config = make_config()
        register_handlers(client, config, completion)
        self.assertEqual(1, len(callbacks))

        chat = object()
        event = SimpleNamespace(get_chat=AsyncMock(return_value=chat))
        await callbacks[0](event)
        completion.sync_channel.assert_awaited_once_with(chat)

        completion.sync_channel = AsyncMock(side_effect=RuntimeError("sync failed"))
        with patch("app.telegram_client.logger.exception") as logged:
            await callbacks[0](event)
        logged.assert_called_once()


if __name__ == "__main__":
    unittest.main()
