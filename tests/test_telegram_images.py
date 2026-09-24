import unittest

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


if __name__ == "__main__":
    unittest.main()
