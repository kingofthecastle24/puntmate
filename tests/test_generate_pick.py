import os, sys, json, unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_pick


def _mock_matches():
    return [{
        "sport": "soccer_fifa_world_cup",
        "match": "France vs Spain",
        "home_team": "France",
        "away_team": "Spain",
        "kickoff": "2026-07-15T19:00:00Z",
        "odds": {"home": 2.50, "away": 2.80, "draw": 3.20},
        "implied_probs": {"home": 0.40, "away": 0.357, "draw": 0.3125},
        "big_game": True,
    }]


def _mock_anthropic_response(payload):
    resp = MagicMock()
    block = MagicMock()
    block.text = json.dumps(payload)
    resp.content = [block]
    return resp


class GeneratePickTests(unittest.TestCase):
    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_defensible_pick_produces_consistent_copy(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "has_selection": True,
            "match": "France vs Spain",
            "sport": "soccer_fifa_world_cup",
            "selection": "France",
            "market": "Head to Head",
            "our_probability": 55,
            "evidence_sufficient": True,
            "confidence": "HIGH",
            "uncertainty_flags": [],
            "reasoning": "France have won four of their last five and Spain are missing a key defender.",
        })
        match_news = {"France vs Spain": {
            "text": "- France football squad update ahead of World Cup match",
            "accepted_count": 3, "warnings": [], "confidence_ceiling": "HIGH",
        }}
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["risk"], "STANDARD_PICK")
        self.assertIn(pick["bet_type"], ("INVESTOR_BET", "PUNTER_BET", "GAMBLER_BET"))
        # No contradictory NO_BET phrases in the generated copy.
        for text in (pick["bet_type_reason"], pick["final_explanation"]):
            self.assertNotIn("sitting this one out", text.lower())
            self.assertNotIn("no pick meets", text.lower())

    @patch("generate_pick.anthropic.Anthropic")
    def test_model_says_no_selection_returns_no_bet_not_a_pick(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "has_selection": False,
            "reasoning": "Nothing here clears the bar today.",
        })
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), {})
        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["risk"], "NO_BET")
        self.assertEqual(pick["bet_type"], "NO_BET")
        # Critically: a NO_BET result must never carry a selection/odds field
        # that a caller could mistakenly render/publish as a live pick.
        self.assertNotIn("selection", pick)
        self.assertNotIn("odds", pick)

    @patch("generate_pick.anthropic.Anthropic")
    def test_confidence_capped_by_validated_research_not_model_opinion(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        # Model claims HIGH confidence but research_validator found zero
        # validated sources for this match -> ceiling is LOW -> gets capped,
        # which (given no other uncertainty flags) should push this to RISKY
        # rather than being taken at face value as a HIGH-confidence STANDARD pick.
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "has_selection": True,
            "match": "France vs Spain",
            "sport": "soccer_fifa_world_cup",
            "selection": "France",
            "market": "Head to Head",
            "our_probability": 55,
            "evidence_sufficient": True,
            "confidence": "HIGH",
            "uncertainty_flags": [],
            "reasoning": "France look sharp.",
        })
        match_news = {"France vs Spain": {"text": "", "accepted_count": 0, "warnings": ["all sources rejected"], "confidence_ceiling": "LOW"}}
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["confidence"], "LOW")
        self.assertEqual(pick["risk"], "RISKY_PICK")

    @patch("generate_pick.anthropic.Anthropic")
    def test_hallucinated_match_not_in_candidates_is_no_bet(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "has_selection": True,
            "match": "Some Other Match Not In List",
            "sport": "soccer_fifa_world_cup",
            "selection": "Team X",
            "market": "Head to Head",
            "our_probability": 60,
            "evidence_sufficient": True,
            "confidence": "HIGH",
            "uncertainty_flags": [],
            "reasoning": "n/a",
        })
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), {})
        self.assertFalse(pick["has_pick"])


if __name__ == "__main__":
    unittest.main()
