"""
Tests for structured rejected-candidate records and the status assigned
when every proposed candidate is dropped (2026-10-11, external audit item
2: "keep estimated probability, bookmaker probability, edge, threshold in
the rejection record" + "separate operational failure from a genuine
no-bet day"). Before this fix, generate_pick_for_matches() labelled EVERY
all-candidates-dropped day BAD_ODDS, even when odds resolved fine and the
value/evidence gate was the only thing that said no — a false operational-
failure alarm on an honest no-value day.
"""
import os, sys, json, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_pick
import run_status


def _mock_match():
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
    block.type = "text"
    block.text = json.dumps(payload)
    resp.content = [block]
    resp.stop_reason = "end_turn"
    return resp


class RejectedCandidateStatusTests(unittest.TestCase):
    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_thin_edge_rejection_is_no_value_not_bad_odds(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "selection": "France",
                "market": "Head to Head",
                "our_probability": 42,  # implied ~40% -> edge ~2pp, below the 7% floor
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [],
                "reasoning": "Thin signal only.",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_match(), {})

        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["status"], run_status.NO_VALUE)
        self.assertNotIn(pick["status"], run_status.OPERATIONAL_FAILURE_STATUSES)

        self.assertEqual(len(pick["rejected_candidates"]), 1)
        rejected = pick["rejected_candidates"][0]
        self.assertEqual(rejected["cause"], "not_backable")
        self.assertIn("our_probability", rejected)
        self.assertIn("implied_probability", rejected)
        self.assertIn("edge_pct", rejected)
        self.assertIn("min_value_edge_pct", rejected)
        self.assertEqual(rejected["min_value_edge_pct"], 7.0)

    @patch("generate_pick.anthropic.Anthropic")
    def test_insufficient_evidence_rejection_gets_its_own_status(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "selection": "France",
                "market": "Head to Head",
                "our_probability": 70,
                "evidence_sufficient": False,  # model itself flags thin basis
                "confidence": "LOW",
                "uncertainty_flags": [],
                "reasoning": "Not enough to go on.",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_match(), {})

        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["status"], run_status.INSUFFICIENT_EVIDENCE)
        self.assertEqual(pick["rejected_candidates"][0]["cause"], "not_backable")
        self.assertFalse(pick["rejected_candidates"][0]["evidence_sufficient"])

    @patch("generate_pick.anthropic.Anthropic")
    def test_unresolvable_odds_is_a_genuine_bad_odds_operational_failure(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "selection": "Some Team Not In This Fixture",
                "market": "Head to Head",
                "our_probability": 60,
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [],
                "reasoning": "n/a",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_match(), {})

        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["status"], run_status.BAD_ODDS)
        self.assertIn(pick["status"], run_status.OPERATIONAL_FAILURE_STATUSES)
        self.assertEqual(pick["rejected_candidates"][0]["cause"], "unresolved_odds")

    @patch("generate_pick.anthropic.Anthropic")
    def test_successful_pick_still_reports_other_rejected_candidates(self, mock_anthropic_cls):
        matches = _mock_match() + [{
            "sport": "rugbyleague_nrl",
            "match": "Warriors vs Broncos",
            "home_team": "Warriors",
            "away_team": "Broncos",
            "kickoff": "2026-07-18T08:00:00Z",
            "odds": {"home": 1.80, "away": 2.05, "draw": None},
            "implied_probs": {"home": 0.5556, "away": 0.4444, "draw": 0},
            "big_game": False,
        }]
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.stream.return_value.__enter__.return_value.get_final_message.return_value = _mock_anthropic_response({
            "candidates": [
                {
                    "match": "France vs Spain",
                    "sport": "soccer_fifa_world_cup",
                    "selection": "France",
                    "market": "Head to Head",
                    "our_probability": 55,
                    "evidence_sufficient": True,
                    "confidence": "HIGH",
                    "uncertainty_flags": [],
                    "reasoning": "Clean edge.",
                },
                {
                    "match": "Warriors vs Broncos",
                    "sport": "rugbyleague_nrl",
                    "selection": "Warriors",
                    "market": "Head to Head",
                    "our_probability": 58,  # implied ~55.6% -> edge ~2.4pp, below floor
                    "evidence_sufficient": True,
                    "confidence": "HIGH",
                    "uncertainty_flags": [],
                    "reasoning": "Thin only.",
                },
            ],
        })
        match_news = {"France vs Spain": {
            "text": "- France football squad update ahead of World Cup match",
            "accepted_count": 3, "warnings": [], "confidence_ceiling": "HIGH",
        }}
        pick = generate_pick.generate_pick_for_matches(matches, match_news)

        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["status"], run_status.PICK_READY)
        self.assertEqual(len(pick["rejected_candidates"]), 1)
        self.assertEqual(pick["rejected_candidates"][0]["match"], "Warriors vs Broncos")


if __name__ == "__main__":
    unittest.main()
