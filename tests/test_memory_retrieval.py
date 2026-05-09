from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from bot import app as bot_app


class MemoryRetrievalTests(unittest.TestCase):
    def test_load_memory_index_reads_transcript_lines(self):
        tmp_dir = Path("tmp") / "tests"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        path = tmp_dir / "transcript.txt"
        path.write_text(
            "[2023-10-18 18:05:03] realtai: zai?\n"
            "[2023-10-18 18:07:16] demosense: ?\n"
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
                "[2023-10-18 18:05:03] realtai: zai?",
                "[2023-10-18 18:07:16] demosense: ?",
                "[2023-10-23 13:14:47] demosense: parcel code 1549",
            ],
        )

        snippets = bot_app.retrieve_memory_snippets("1549", index, limit=2)

        self.assertEqual(len(snippets), 1)
        self.assertEqual(snippets[0], "[2023-10-23 13:14:47] demosense: parcel code 1549")

    def test_build_system_prompt_keeps_skill_minimal_and_uses_raw_memory(self):
        prompt = bot_app.build_system_prompt(
            "MINIMAL SKILL RULES",
            ["[2023-10-23 13:14:47] demosense: parcel code 1549"],
        )

        self.assertIn("MINIMAL SKILL RULES", prompt)
        self.assertIn("lowest-level safety and evidence rules", prompt)
        self.assertIn("Raw retrieved chat-memory snippets", prompt)
        self.assertIn("Do not invent memories", prompt)
        self.assertIn("persona, tone, and memory from raw retrieved chat-memory snippets", prompt)
        self.assertIn("parcel code 1549", prompt)

    def test_health_reports_raw_transcript_first_persona_mode(self):
        with TestClient(bot_app.app) as client:
            response = client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["persona_mode"], "raw_transcript_first")


if __name__ == "__main__":
    unittest.main()
