import unittest

from bot import app as bot_app


class TelegramSplittingTests(unittest.TestCase):
    def test_split_telegram_text_sends_lines_as_separate_messages(self):
        chunks = bot_app.split_telegram_text("第一条\n第二条")

        self.assertEqual(chunks, ["第一条", "第二条"])

    def test_split_telegram_text_ignores_blank_lines_between_messages(self):
        chunks = bot_app.split_telegram_text("第一条\n\n第二条")

        self.assertEqual(chunks, ["第一条", "第二条"])

    def test_split_telegram_text_still_splits_long_lines_by_limit(self):
        chunks = bot_app.split_telegram_text("abcdef", limit=3)

        self.assertEqual(chunks, ["abc", "def"])


if __name__ == "__main__":
    unittest.main()
