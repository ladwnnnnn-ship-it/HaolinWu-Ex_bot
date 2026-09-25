from pathlib import Path
import unittest


SKILL_PATH = Path("exes/demosense/SKILL.md")


class SkillStyleControlsTests(unittest.TestCase):
    @unittest.skipUnless(
        SKILL_PATH.exists(),
        "private demosense persona is not present in this clean checkout",
    )
    def test_skill_contains_patience_and_softening_controls(self):
        skill = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn("Use filler particles sparingly", skill)
        self.assertIn("Keep impatience and disgust low-intensity", skill)
        self.assertIn("Avoid piling on rhetorical questions", skill)
        self.assertIn("Assume patience first", skill)

    @unittest.skipUnless(
        SKILL_PATH.exists(),
        "private demosense persona is not present in this clean checkout",
    )
    def test_skill_allows_grounded_visual_evidence(self):
        skill = SKILL_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "Only treat media as unseen when no grounded visual evidence is provided",
            skill,
        )
        self.assertIn(
            "must not claim that she cannot see the image",
            skill,
        )


if __name__ == "__main__":
    unittest.main()
