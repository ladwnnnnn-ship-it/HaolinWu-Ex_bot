from pathlib import Path
import unittest

from bot import app as bot_app


class MemoryRetrievalTests(unittest.TestCase):
    def test_load_memory_index_reads_transcript_lines(self):
        tmp_dir = Path("tmp") / "tests"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / "transcript.txt"
        path.write_text(
            "[2023-10-18 18:05:03] realtai: 在？\n"
            "[2023-10-18 18:07:16] demosense: ？\n"
            "\n",
            encoding="utf-8",
        )

        index = bot_app.load_memory_index(path)

        self.assertEqual(index.loaded, True)
        self.assertEqual(index.count, 2)
        self.assertIn("demosense", index.lines[1])

    def test_retrieve_memory_snippets_uses_raw_matching_lines(self):
        index = bot_app.MemoryIndex(
            path="memory.txt",
            loaded=True,
            lines=[
                "[2023-10-18 18:05:03] realtai: 在？",
                "[2023-10-18 18:07:16] demosense: ？",
                "[2023-10-23 13:14:47] demosense: 尾号1549收件名卿卿",
            ],
        )

        snippets = bot_app.retrieve_memory_snippets("收件名是什么", index, limit=2)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0], "[2023-10-23 13:14:47] demosense: 尾号1549收件名卿卿")

    def test_build_system_prompt_keeps_skill_as_source_of_truth_and_marks_raw_memory(self):
        prompt = bot_app.build_system_prompt(
            "SKILL BODY",
            ["[2023-10-23 13:14:47] demosense: 尾号1549收件名卿卿"],
        )

        self.assertIn("SKILL BODY", prompt)
        self.assertIn("highest-priority persona rule", prompt)
        self.assertIn("Raw retrieved chat-memory snippets", prompt)
        self.assertIn("Do not invent memories", prompt)
        self.assertIn("尾号1549收件名卿卿", prompt)


if __name__ == "__main__":
    unittest.main()
