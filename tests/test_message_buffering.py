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

    def test_rule_waits_longer_for_unfinished_messages(self):
        wait_seconds = bot_app.estimate_message_idle_seconds(
            ["我今天其实想说", "就是"],
            base_seconds=8,
            unfinished_bonus_seconds=10,
            max_seconds=25,
        )

        self.assertEqual(wait_seconds, 18)

    def test_rule_waits_less_for_clear_questions(self):
        wait_seconds = bot_app.estimate_message_idle_seconds(
            ["你还记得那天吗？"],
            base_seconds=8,
            question_discount_seconds=3,
            min_seconds=3,
        )

        self.assertEqual(wait_seconds, 5)

    def test_default_rule_feels_fast_for_complete_messages(self):
        wait_seconds = bot_app.estimate_message_idle_seconds(["我到家了"])

        self.assertEqual(wait_seconds, 3)

    def test_default_rule_still_waits_for_unfinished_messages(self):
        wait_seconds = bot_app.estimate_message_idle_seconds(["我想说"])

        self.assertEqual(wait_seconds, 15)

    async def test_model_completion_decision_can_shorten_buffer_wait(self):
        handled = []
        handled_event = asyncio.Event()

        async def fake_handle(chat_id, text):
            handled.append((chat_id, text))
            handled_event.set()

        async def fake_completion_decision(messages):
            await asyncio.sleep(0.005)
            return {"complete": True, "wait_seconds": 0.01}

        originals = (
            bot_app.handle_text_message,
            bot_app.call_message_completion_decision,
            bot_app.settings.message_min_idle_seconds,
        )
        bot_app.handle_text_message = fake_handle
        bot_app.call_message_completion_decision = fake_completion_decision
        bot_app.settings.message_min_idle_seconds = 0
        try:
            await bot_app.handle_buffered_text_message(
                123,
                "你觉得呢？",
                idle_seconds=0.05,
                completion_timeout=0.03,
            )
            await asyncio.wait_for(handled_event.wait(), timeout=0.2)
        finally:
            (
                bot_app.handle_text_message,
                bot_app.call_message_completion_decision,
                bot_app.settings.message_min_idle_seconds,
            ) = originals

        self.assertEqual(handled, [(123, "你觉得呢？")])

    async def test_slow_model_completion_decision_falls_back_to_rule_wait(self):
        handled = []
        handled_event = asyncio.Event()

        async def fake_handle(chat_id, text):
            handled.append((chat_id, text))
            handled_event.set()

        async def slow_completion_decision(messages):
            await asyncio.sleep(0.1)
            return {"complete": False, "wait_seconds": 0.1}

        originals = (
            bot_app.handle_text_message,
            bot_app.call_message_completion_decision,
        )
        bot_app.handle_text_message = fake_handle
        bot_app.call_message_completion_decision = slow_completion_decision
        try:
            await bot_app.handle_buffered_text_message(
                123,
                "普通一句",
                idle_seconds=0.02,
                completion_timeout=0.005,
            )
            await asyncio.wait_for(handled_event.wait(), timeout=0.2)
        finally:
            (
                bot_app.handle_text_message,
                bot_app.call_message_completion_decision,
            ) = originals

        self.assertEqual(handled, [(123, "普通一句")])


if __name__ == "__main__":
    unittest.main()
