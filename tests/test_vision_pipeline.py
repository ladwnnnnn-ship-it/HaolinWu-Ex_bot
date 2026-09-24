import unittest

from bot.vision import (
    ImageObservation,
    build_vision_payload,
    call_vision_api,
    parse_vision_response,
)


class FakeResponse:
    def __init__(self, *, json_data, status_code=200, text=""):
        self._json_data = json_data
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")

    def json(self):
        return self._json_data


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return self.responses.pop(0)


class VisionResponseTests(unittest.TestCase):
    def test_parses_grounded_image_observation(self):
        raw = '''{
          "summary": "桌上有一杯带冰块的浅棕色饮品",
          "visible_text": ["LATTE"],
          "objects": ["透明塑料杯", "吸管", "冰块"],
          "likely_items": [{"name": "冰拿铁", "confidence": 0.78}],
          "uncertainties": ["无法确认咖啡品牌"]
        }'''

        result = parse_vision_response(raw)

        self.assertIsInstance(result, ImageObservation)
        self.assertEqual(result.likely_items[0]["name"], "冰拿铁")
        self.assertEqual(result.visible_text, ["LATTE"])

    def test_invalid_json_becomes_uncertain_observation(self):
        result = parse_vision_response("not json")

        self.assertEqual(result.summary, "图片识别结果不可用")
        self.assertEqual(result.likely_items, [])
        self.assertTrue(result.uncertainties)


class VisionPayloadTests(unittest.TestCase):
    def test_builds_deepseek_flash_multimodal_payload(self):
        payload = build_vision_payload(
            image_bytes=b"jpeg-data",
            mime_type="image/jpeg",
            caption="猜猜我喝的什么",
            model="deepseek-flash",
        )

        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        content = payload["messages"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("猜猜我喝的什么", content[0]["text"])
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(
            content[1]["image_url"]["url"].startswith(
                "data:image/jpeg;base64,"
            )
        )


class VisionApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_vision_endpoint_and_parses_observation(self):
        client = FakeClient(
            [
                FakeResponse(
                    json_data={
                        "choices": [{
                            "message": {
                                "content": '{"summary":"一杯咖啡","visible_text":[],"objects":["杯子"],"likely_items":[{"name":"拿铁","confidence":0.8}],"uncertainties":[]}'
                            }
                        }]
                    }
                )
            ]
        )

        result = await call_vision_api(
            image_bytes=b"jpeg-data",
            mime_type="image/jpeg",
            caption="这是什么",
            api_base="https://api.deepseek.com/v1",
            api_key="secret",
            model="deepseek-flash",
            client=client,
        )

        self.assertEqual(result.summary, "一杯咖啡")
        self.assertEqual(
            client.requests[0][0],
            "https://api.deepseek.com/v1/chat/completions",
        )
        self.assertEqual(
            client.requests[0][1]["headers"],
            {"Authorization": "Bearer secret"},
        )

    async def test_retries_once_without_response_format_when_rejected(self):
        success_body = {
            "choices": [{
                "message": {
                    "content": '{"summary":"图片","visible_text":[],"objects":[],"likely_items":[],"uncertainties":[]}'
                }
            }]
        }
        client = FakeClient(
            [
                FakeResponse(
                    json_data={"error": "unsupported"},
                    status_code=400,
                    text="response_format is not supported",
                ),
                FakeResponse(json_data=success_body),
            ]
        )

        await call_vision_api(
            image_bytes=b"jpeg-data",
            mime_type="image/jpeg",
            caption="",
            api_base="https://provider.example/v1",
            api_key="secret",
            model="deepseek-flash",
            client=client,
        )

        self.assertEqual(len(client.requests), 2)
        self.assertIn("response_format", client.requests[0][1]["json"])
        self.assertNotIn("response_format", client.requests[1][1]["json"])


if __name__ == "__main__":
    unittest.main()
