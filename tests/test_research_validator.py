import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from research_validator import validate_snippets, assess_evidence_strength


class ResearchValidatorTests(unittest.TestCase):
    def test_rejects_cross_sport_contamination(self):
        # This is the exact real-world bug: NRL content for a football fixture.
        snippets = ["France NRL 2025 preview: Warriors edge trainers"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any("wrong sport" in w for w in warnings))

    def test_rejects_team_name_only_match(self):
        snippets = ["France announces new tourism campaign"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(accepted, [])

    def test_accepts_genuinely_relevant_snippet(self):
        snippets = ["France football squad injury update ahead of World Cup match"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(len(accepted), 1)

    def test_confidence_ceiling_zero_sources(self):
        # Phase 1: zero validated news no longer caps at LOW — Claude is now
        # allowed to use general team/competition knowledge as supporting
        # context, so zero fresh snippets isn't "zero evidence" anymore.
        ceiling, warnings = assess_evidence_strength([])
        self.assertEqual(ceiling, "MODERATE")

    def test_confidence_ceiling_full_sources(self):
        ceiling, warnings = assess_evidence_strength(["a", "b", "c"], requested_count=3)
        self.assertEqual(ceiling, "HIGH")


if __name__ == "__main__":
    unittest.main()
