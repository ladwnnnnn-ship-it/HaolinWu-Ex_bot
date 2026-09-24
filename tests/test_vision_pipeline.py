import unittest

from bot.vision import ImageObservation, parse_vision_response


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


if __name__ == "__main__":
    unittest.main()
