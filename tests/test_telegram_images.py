import asyncio
import os
import unittest

os.environ.setdefault("PERSONA_TEXT", "TEST PERSONA")

from bot import app as bot_app
from bot.vision import TelegramPhoto, download_telegram_photo, select_telegram_photo


class FakeResponse:
    def __init__(self, *, json_data=None, content=b"", content_type="application/json"):
        self._json_data = json_data
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def get(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class TelegramPhotoSelectionTests(unittest.TestCase):
    def test_selects_largest_telegram_photo(self):
        message = {
            "photo": [
                {"file_id": "small", "width": 90, "height": 90, "file_size": 1000},
                {"file_id": "large", "width": 1280, "height": 960, "file_size": 120000},
            ],
            "caption": "猜猜我喝的什么",
        }

        photo = select_telegram_photo(message)

        self.assertEqual(photo.file_id, "large")
        self.assertEqual(photo.caption, "猜猜我喝的什么")

    def test_message_without_photo_returns_none(self):
        self.assertIsNone(select_telegram_photo({"text": "你好"}))


class TelegramPhotoDownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_downloads_file_from_telegram_path(self):
        client = FakeClient(
            [
                FakeResponse(json_data={"result": {"file_path": "photos/example.jpg"}}),
                FakeResponse(content=b"jpeg-data", content_type="image/jpeg"),
            ]
        )
        photo = TelegramPhoto(file_id="large", caption="咖啡", declared_size=9)

        image_bytes, mime_type = await download_telegram_photo(
            photo,
            telegram_api="https://api.telegram.org/botTOKEN",
            bot_token="TOKEN",
            client=client,
            max_bytes=100,
        )

        self.assertEqual(image_bytes, b"jpeg-data")
        self.assertEqual(mime_type, "image/jpeg")
        self.assertEqual(
            client.requests,
            [
                (
                    "https://api.telegram.org/botTOKEN/getFile",
                    {"params": {"file_id": "large"}},
                ),
                (
                    "https://api.telegram.org/file/botTOKEN/photos/example.jpg",
                    {},
                ),
            ],
        )

    async def test_rejects_declared_oversized_photo_before_downloading(self):
        client = FakeClient([])
        photo = TelegramPhoto(file_id="large", declared_size=101)

        with self.assertRaisesRegex(ValueError, "exceeds"):
            await download_telegram_photo(
                photo,
                telegram_api="https://api.telegram.org/botTOKEN",
                bot_token="TOKEN",
                client=client,
                max_bytes=100,
            )

        self.assertEqual(client.requests, [])

    async def test_detects_jpeg_when_telegram_uses_octet_stream(self):
        jpeg_bytes = b"\xff\xd8\xff\xe0jpeg-data"
        client = FakeClient(
            [
                FakeResponse(json_data={"result": {"file_path": "photos/example.jpg"}}),
                FakeResponse(
                    content=jpeg_bytes,
                    content_type="application/octet-stream",
                ),
            ]
        )
        photo = TelegramPhoto(file_id="large", declared_size=len(jpeg_bytes))

        try:
            image_bytes, mime_type = await download_telegram_photo(
                photo,
                telegram_api="https://api.telegram.org/botTOKEN",
                bot_token="TOKEN",
                client=client,
                max_bytes=100,
            )
        except ValueError as exc:
            self.fail(f"JPEG bytes should override a generic content type: {exc}")

        self.assertEqual(image_bytes, jpeg_bytes)
        self.assertEqual(mime_type, "image/jpeg")

    async def test_rejects_unsupported_mime_type(self):
        client = FakeClient(
            [
                FakeResponse(json_data={"result": {"file_path": "files/not-image"}}),
                FakeResponse(content=b"html", content_type="text/html; charset=utf-8"),
            ]
        )
        photo = TelegramPhoto(file_id="large", declared_size=4)

        with self.assertRaisesRegex(ValueError, "Unsupported image MIME"):
            await download_telegram_photo(
                photo,
                telegram_api="https://api.telegram.org/botTOKEN",
                bot_token="TOKEN",
                client=client,
                max_bytes=100,
            )


class TelegramImageBufferTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot_app._pending_message_buffers.clear()
        bot_app._chat_processing_locks.clear()

    async def asyncTearDown(self):
        for state in bot_app._pending_message_buffers.values():
            if state.task:
                state.task.cancel()
        await asyncio.gather(
            *[
                state.task
                for state in bot_app._pending_message_buffers.values()
                if state.task
            ],
            return_exceptions=True,
        )
        bot_app._pending_message_buffers.clear()
        bot_app._chat_processing_locks.clear()

    async def test_buffers_photo_with_followup_text_as_one_turn(self):
        handled = []

        async def fake_handle(chat_id, text, photos):
            handled.append((chat_id, text, photos))

        original = bot_app.handle_image_message
        bot_app.handle_image_message = fake_handle
        photo = TelegramPhoto(file_id="large", caption="猜猜我喝的什么")
        try:
            await bot_app.handle_buffered_user_message(
                123,
                text="猜猜我喝的什么",
                photo=photo,
                idle_seconds=0.03,
            )
            await bot_app.handle_buffered_user_message(
                123,
                text="看出来了吗",
                idle_seconds=0.03,
            )
            await asyncio.sleep(0.06)
        finally:
            bot_app.handle_image_message = original

        self.assertEqual(len(handled), 1)
        self.assertEqual(handled[0][0:2], (123, "猜猜我喝的什么\n看出来了吗"))
        self.assertEqual(handled[0][2], [photo])

    async def test_photo_without_caption_is_still_flushed(self):
        handled = []

        async def fake_handle(chat_id, text, photos):
            handled.append((chat_id, text, photos))

        original = bot_app.handle_image_message
        bot_app.handle_image_message = fake_handle
        photo = TelegramPhoto(file_id="large")
        try:
            await bot_app.handle_buffered_user_message(
                123,
                text="",
                photo=photo,
                idle_seconds=0.02,
            )
            await asyncio.sleep(0.05)
        finally:
            bot_app.handle_image_message = original

        self.assertEqual(handled, [(123, "", [photo])])

    async def test_next_text_waits_for_inflight_image_turn_in_same_chat(self):
        events = []
        image_started = asyncio.Event()
        release_image = asyncio.Event()
        image_finished = asyncio.Event()
        text_started = asyncio.Event()
        text_finished = asyncio.Event()

        async def fake_handle_image(chat_id, text, photos):
            events.append("image_start")
            image_started.set()
            await release_image.wait()
            events.append("image_end")
            image_finished.set()

        async def fake_handle_text(chat_id, text):
            events.append("text")
            text_started.set()
            text_finished.set()

        original_image = bot_app.handle_image_message
        original_text = bot_app.handle_text_message
        bot_app.handle_image_message = fake_handle_image
        bot_app.handle_text_message = fake_handle_text
        try:
            await bot_app.handle_buffered_user_message(
                456,
                photo=TelegramPhoto(file_id="large"),
                idle_seconds=0,
            )
            await asyncio.wait_for(image_started.wait(), timeout=0.2)
            await bot_app.handle_buffered_user_message(
                456,
                text="我已经发了",
                idle_seconds=0,
            )
            await asyncio.sleep(0.03)
            text_started_before_image_finished = text_started.is_set()
            release_image.set()
            await asyncio.wait_for(image_finished.wait(), timeout=0.2)
            await asyncio.wait_for(text_finished.wait(), timeout=0.2)
        finally:
            release_image.set()
            bot_app.handle_image_message = original_image
            bot_app.handle_text_message = original_text

        self.assertFalse(text_started_before_image_finished)
        self.assertEqual(events, ["image_start", "image_end", "text"])


class TelegramImageWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_webhook_accepts_photo_without_text(self):
        buffered = []
        recorded = []

        class FakeRequest:
            async def json(self):
                return {
                    "message": {
                        "chat": {"id": 123},
                        "photo": [
                            {"file_id": "small", "width": 90, "height": 90},
                            {"file_id": "large", "width": 1280, "height": 960},
                        ],
                        "caption": "猜猜这是什么",
                    }
                }

        async def fake_buffer(chat_id, **kwargs):
            buffered.append((chat_id, kwargs))

        async def fake_record(chat_id, when=None):
            recorded.append(chat_id)

        originals = (
            bot_app.settings.telegram_webhook_secret,
            bot_app.handle_buffered_user_message,
            bot_app.record_user_chat_activity,
        )
        (
            bot_app.settings.telegram_webhook_secret,
            bot_app.handle_buffered_user_message,
            bot_app.record_user_chat_activity,
        ) = ("secret", fake_buffer, fake_record)
        try:
            result = await bot_app.telegram_webhook(
                "secret",
                FakeRequest(),
                x_telegram_bot_api_secret_token=None,
            )
        finally:
            (
                bot_app.settings.telegram_webhook_secret,
                bot_app.handle_buffered_user_message,
                bot_app.record_user_chat_activity,
            ) = originals

        self.assertEqual(result, {"ok": True})
        self.assertEqual(recorded, [123])
        self.assertEqual(buffered[0][0], 123)
        self.assertEqual(buffered[0][1]["text"], "猜猜这是什么")
        self.assertEqual(buffered[0][1]["photo"].file_id, "large")


if __name__ == "__main__":
    unittest.main()
