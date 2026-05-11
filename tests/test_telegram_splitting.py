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


class TelegramCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_chatid_command_returns_current_chat_id(self):
        sent = []

        async def fake_send(chat_id, text):
            sent.append((chat_id, text))

        original = bot_app.send_telegram_message
        bot_app.send_telegram_message = fake_send
        try:
            await bot_app.handle_text_message(123456, "/chatid")
        finally:
            bot_app.send_telegram_message = original

        self.assertEqual(sent, [(123456, "chat_id: 123456")])


if __name__ == "__main__":
    unittest.main()
