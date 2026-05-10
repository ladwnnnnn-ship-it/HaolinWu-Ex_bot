from datetime import datetime, timezone, timedelta
import unittest

from bot import app as bot_app


class ProactiveMessageTests(unittest.IsolatedAsyncioTestCase):
    def test_build_initiation_profile_uses_persona_messages_after_idle_gaps(self):
        index = bot_app.MemoryIndex(
            path="memory.txt",
            loaded=True,
            lines=[
                "[2024-01-01 08:00:00] realtai.: 在？",
                "[2024-01-01 08:01:00] demosense: ？",
                "[2024-01-01 12:30:00] demosense: 不好意思打扰一下",
                "[2024-01-01 12:31:00] demosense: 能帮我带饭吗",
                "[2024-01-01 22:10:00] demosense: 在不在",
            ],
        )

        profile = bot_app.build_initiation_profile(index, gap_hours=4)

        self.assertIn("12:00(1)", profile.stats)
        self.assertIn("22:00(1)", profile.stats)
        self.assertIn("[2024-01-01 12:30] 不好意思打扰一下", profile.examples)
        self.assertNotIn("能帮我带饭吗", profile.examples)

    def test_proactive_prompts_preserve_restraint_and_output_contracts(self):
        decision_prompt = bot_app.build_proactive_decision_prompt(
            local_time="2026-05-11 22:13",
            idle_hours=12.5,
            already_sent_today=False,
            initiation_stats="12:00(45), 22:00(23)",
            recent_history="user: 昨天有点累",
            persona_prompt="SKILL BODY",
        )
        message_prompt = bot_app.build_proactive_message_prompt(
            local_time="2026-05-11 22:13",
            intent="late_night_ping",
            initiation_examples="[2024-01-01 22:10] 在不在",
            recent_history="user: 昨天有点累",
            persona_prompt="PERSONA",
        )

        self.assertIn("Return exactly one JSON object", decision_prompt)
        self.assertIn('"should_send"', decision_prompt)
        self.assertIn("Do not initiate just because the system tick happened", decision_prompt)
        self.assertIn("SKILL BODY", decision_prompt)
        self.assertIn("Do not sound like an assistant", message_prompt)
        self.assertIn("Output only the Telegram message text", message_prompt)
        self.assertIn("PERSONA", message_prompt)

    async def test_proactive_tick_sends_generated_message_when_decision_allows(self):
        sent = []
        marked = []
        now = datetime(2026, 5, 11, 22, 13, tzinfo=timezone(timedelta(hours=8)))

        async def fake_known_chats():
            return ["123"]

        async def fake_last_user_at(chat_id):
            return now - timedelta(hours=13)

        async def fake_sent_date(chat_id):
            return None

        async def fake_decision(*args, **kwargs):
            return {"should_send": True, "intent": "late_night_ping", "reason": "matches 22:00"}

        async def fake_message(*args, **kwargs):
            return "在不在"

        async def fake_send(chat_id, text):
            sent.append((chat_id, text))

        async def fake_mark(chat_id, sent_date):
            marked.append((chat_id, sent_date))

        test_index = bot_app.MemoryIndex(
            path="memory.txt",
            loaded=True,
            lines=["[2024-01-01 22:10:00] demosense: 在不在"],
        )
        originals = (
            bot_app.list_known_chats,
            bot_app.get_last_user_message_at,
            bot_app.get_last_proactive_sent_date,
            bot_app.call_proactive_decision,
            bot_app.call_proactive_message,
            bot_app.send_telegram_message,
            bot_app.mark_proactive_sent,
            bot_app.MEMORY_INDEX,
        )
        (
            bot_app.list_known_chats,
            bot_app.get_last_user_message_at,
            bot_app.get_last_proactive_sent_date,
            bot_app.call_proactive_decision,
            bot_app.call_proactive_message,
            bot_app.send_telegram_message,
            bot_app.mark_proactive_sent,
            bot_app.MEMORY_INDEX,
        ) = (
            fake_known_chats,
            fake_last_user_at,
            fake_sent_date,
            fake_decision,
            fake_message,
            fake_send,
            fake_mark,
            test_index,
        )
        try:
            result = await bot_app.run_proactive_tick(now=now)
        finally:
            (
                bot_app.list_known_chats,
                bot_app.get_last_user_message_at,
                bot_app.get_last_proactive_sent_date,
                bot_app.call_proactive_decision,
                bot_app.call_proactive_message,
                bot_app.send_telegram_message,
                bot_app.mark_proactive_sent,
                bot_app.MEMORY_INDEX,
            ) = originals

        self.assertEqual(result, {"checked": 1, "sent": 1})
        self.assertEqual(sent, [("123", "在不在")])
        self.assertEqual(marked, [("123", "2026-05-11")])


if __name__ == "__main__":
    unittest.main()
