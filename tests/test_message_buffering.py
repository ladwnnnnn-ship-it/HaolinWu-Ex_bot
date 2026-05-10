import asyncio
import unittest

from bot import app as bot_app


class MessageBufferingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        bot_app._pending_message_buffers.clear()

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

    async def test_batches_quick_user_messages_until_idle(self):
        handled = []

        async def fake_handle(chat_id, text):
            handled.append((chat_id, text))

        original = bot_app.handle_text_message
        bot_app.handle_text_message = fake_handle
        try:
            await bot_app.handle_buffered_text_message(123, "第一句", idle_seconds=0.03)
            await bot_app.handle_buffered_text_message(123, "第二句", idle_seconds=0.03)
            await bot_app.handle_buffered_text_message(123, "第三句", idle_seconds=0.03)
            await asyncio.sleep(0.06)
        finally:
            bot_app.handle_text_message = original

        self.assertEqual(handled, [(123, "第一句\n第二句\n第三句")])

    async def test_keeps_different_chats_in_separate_batches(self):
        handled = []

        async def fake_handle(chat_id, text):
            handled.append((chat_id, text))

        original = bot_app.handle_text_message
        bot_app.handle_text_message = fake_handle
        try:
            await bot_app.handle_buffered_text_message(123, "A1", idle_seconds=0.03)
            await bot_app.handle_buffered_text_message(456, "B1", idle_seconds=0.03)
            await bot_app.handle_buffered_text_message(123, "A2", idle_seconds=0.03)
            await asyncio.sleep(0.06)
        finally:
            bot_app.handle_text_message = original

        self.assertCountEqual(handled, [(123, "A1\nA2"), (456, "B1")])

    async def test_commands_run_immediately_and_clear_pending_messages(self):
        handled = []

        async def fake_handle(chat_id, text):
            handled.append((chat_id, text))

        original = bot_app.handle_text_message
        bot_app.handle_text_message = fake_handle
        try:
            await bot_app.handle_buffered_text_message(123, "还没说完", idle_seconds=0.03)
            await bot_app.handle_buffered_text_message(123, "/reset", idle_seconds=0.03)
            await asyncio.sleep(0.06)
        finally:
            bot_app.handle_text_message = original

        self.assertEqual(handled, [(123, "/reset")])


if __name__ == "__main__":
    unittest.main()
