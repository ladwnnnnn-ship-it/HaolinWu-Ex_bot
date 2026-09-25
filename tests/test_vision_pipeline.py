import logging
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("PERSONA_TEXT", "TEST PERSONA")

from bot import app as bot_app
from bot.vision import (
    ImageObservation,
    TelegramPhoto,
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

    def test_system_prompt_includes_grounded_visual_observation(self):
        observation = ImageObservation(
            summary="桌上有一杯浅棕色饮品",
            likely_items=[{"name": "拿铁", "confidence": 0.65}],
            uncertainties=["无法确认品牌"],
        )

        prompt = bot_app.build_system_prompt(
            "PERSONA",
            image_observation=observation,
        )

        self.assertIn("桌上有一杯浅棕色饮品", prompt)
        self.assertIn("confidence 低于 0.7", prompt)
        self.assertIn("不得补充", prompt)


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


class ImageMessagePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_image_observation_reaches_language_model_not_binary_history(self):
        observation = ImageObservation(
            summary="桌上有一杯冰拿铁",
            objects=["透明杯", "冰块"],
            likely_items=[{"name": "冰拿铁", "confidence": 0.82}],
        )
        llm_calls = []
        saved = []
        sent = []

        async def fake_analyze(photo):
            return observation

        async def fake_load(chat_id):
            return []

        async def fake_llm(text, history, image_observation=None):
            llm_calls.append((text, history, image_observation))
            return "冰拿铁？\n你还挺会享受"

        async def fake_save(chat_id, history):
            saved.append((chat_id, history))

        async def fake_send(chat_id, text):
            sent.append((chat_id, text))

        photo = TelegramPhoto(file_id="large", caption="猜猜我喝的什么")
        with (
            patch.object(bot_app, "analyze_telegram_photo", fake_analyze, create=True),
            patch.object(bot_app, "load_history", fake_load),
            patch.object(bot_app, "call_llm", fake_llm),
            patch.object(bot_app, "save_history", fake_save),
            patch.object(bot_app, "send_telegram_message", fake_send),
        ):
            await bot_app.handle_image_message(
                123,
                "猜猜我喝的什么",
                [photo],
            )

        self.assertEqual(llm_calls[0][0], "猜猜我喝的什么")
        self.assertIs(llm_calls[0][2], observation)
        stored_history = saved[0][1]
        self.assertIn("桌上有一杯冰拿铁", stored_history[0]["content"])
        self.assertNotIn("data:image", stored_history[0]["content"])
        self.assertEqual(sent, [(123, "冰拿铁？\n你还挺会享受")])

    async def test_vision_failure_is_passed_as_uncertainty_instead_of_crashing(self):
        llm_observations = []

        async def failing_analyze(photo):
            raise RuntimeError("provider unavailable")

        async def fake_load(chat_id):
            return []

        async def fake_llm(text, history, image_observation=None):
            llm_observations.append(image_observation)
            return "图没加载出来\n再发一下"

        async def noop(*args, **kwargs):
            return None

        with (
            patch.object(bot_app, "analyze_telegram_photo", failing_analyze, create=True),
            patch.object(bot_app, "load_history", fake_load),
            patch.object(bot_app, "call_llm", fake_llm),
            patch.object(bot_app, "save_history", noop),
            patch.object(bot_app, "send_telegram_message", noop),
        ):
            await bot_app.handle_image_message(
                123,
                "看得出来吗",
                [TelegramPhoto(file_id="large")],
            )

        self.assertEqual(llm_observations[0].summary, "图片识别结果不可用")
        self.assertTrue(llm_observations[0].uncertainties)


class VisionHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_reports_vision_configuration_without_key(self):
        originals = (
            bot_app.settings.vision_api_base,
            bot_app.settings.vision_api_key,
            bot_app.settings.vision_model,
        )
        (
            bot_app.settings.vision_api_base,
            bot_app.settings.vision_api_key,
            bot_app.settings.vision_model,
        ) = (
            "https://api.deepseek.com/v1",
            "super-secret",
            "deepseek-flash",
        )
        try:
            result = await bot_app.health()
        finally:
            (
                bot_app.settings.vision_api_base,
                bot_app.settings.vision_api_key,
                bot_app.settings.vision_model,
            ) = originals

        self.assertEqual(result["vision"]["configured"], True)
        self.assertEqual(result["vision"]["model"], "deepseek-flash")
        self.assertNotIn("super-secret", repr(result))

    def test_httpx_info_logging_is_disabled_to_protect_bot_token(self):
        self.assertGreaterEqual(logging.getLogger("httpx").level, logging.WARNING)


if __name__ == "__main__":
    unittest.main()
