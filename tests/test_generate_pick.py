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


def _mock_matches_with_extra_markets():
    return [{
        "sport": "rugbyleague_nrl",
        "match": "Warriors vs Broncos",
        "home_team": "Warriors",
        "away_team": "Broncos",
        "kickoff": "2026-07-18T08:00:00Z",
        "odds": {"home": 1.80, "away": 2.05, "draw": None},
        "implied_probs": {"home": 0.5324, "away": 0.4676, "draw": 0},
        "markets_extra": {
            "spreads": {
                "home": {"point": -6.5, "price": 1.90},
                "away": {"point": 6.5, "price": 1.90},
            },
            "totals": {
                "over": {"point": 42.5, "price": 1.87},
                "under": {"point": 42.5, "price": 1.93},
            },
        },
        "big_game": False,
    }]


def _mock_two_matches_investor_and_gambler():
    """Two independent matches: one where a genuinely Investor-grade
    candidate exists (short odds, HIGH confidence, clears edge), and one
    where only a Gambler-grade candidate exists (long odds, MODERATE
    confidence, clears edge but with a risky-signal). Used to test Phase 2's
    Investor-first tie-break when both are genuinely defensible same day."""
    return [
        {
            "sport": "rugbyleague_nrl",
            "match": "Warriors vs Broncos",
            "home_team": "Warriors",
            "away_team": "Broncos",
            "kickoff": "2026-07-18T08:00:00Z",
            "odds": {"home": 1.80, "away": 2.05, "draw": None},
            "implied_probs": {"home": 0.5556, "away": 0.4444, "draw": 0},
            "big_game": False,
        },
        {
            "sport": "soccer_fifa_world_cup",
            "match": "France vs Spain",
            "home_team": "France",
            "away_team": "Spain",
            "kickoff": "2026-07-15T19:00:00Z",
            "odds": {"home": 2.50, "away": 3.50, "draw": 3.20},
            "implied_probs": {"home": 0.40, "away": 0.2857, "draw": 0.3125},
            "big_game": True,
        },
    ]


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
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "selection": "France",
                "market": "Head to Head",
                "our_probability": 55,
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [],
                "reasoning": "France have won four of their last five and Spain are missing a key defender.",
            }],
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
    def test_model_returns_no_candidates_is_no_bet_not_a_pick(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [],
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
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "selection": "France",
                "market": "Head to Head",
                "our_probability": 55,
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [],
                "reasoning": "France look sharp.",
            }],
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
            "candidates": [{
                "match": "Some Other Match Not In List",
                "sport": "soccer_fifa_world_cup",
                "selection": "Team X",
                "market": "Head to Head",
                "our_probability": 60,
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [],
                "reasoning": "n/a",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), {})
        self.assertFalse(pick["has_pick"])

    @patch("generate_pick.anthropic.Anthropic")
    def test_spread_market_selection_resolves_correct_odds_and_line(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "Warriors vs Broncos",
                "sport": "rugbyleague_nrl",
                "market_type": "spread",
                "selection": "Warriors",
                "line": -6.5,
                "market": "Handicap",
                "our_probability": 58,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": [],
                "reasoning": "Warriors have covered this line at home all season and Broncos are missing forwards.",
            }],
        })
        match_news = {"Warriors vs Broncos": {
            "text": "- Warriors named full-strength side", "accepted_count": 2,
            "warnings": [], "confidence_ceiling": "MODERATE",
        }}
        pick = generate_pick.generate_pick_for_matches(_mock_matches_with_extra_markets(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["market_type"], "spread")
        self.assertEqual(pick["odds"], "1.90")
        self.assertIn("WARRIORS", pick["selection"])
        self.assertIn("-6.5", pick["selection"])

    @patch("generate_pick.anthropic.Anthropic")
    def test_total_market_selection_resolves_correct_odds_and_line(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "Warriors vs Broncos",
                "sport": "rugbyleague_nrl",
                "market_type": "total",
                "selection": "Over",
                "line": 42.5,
                "market": "Total",
                "our_probability": 56,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": [],
                "reasoning": "Both sides have leaked points defensively the last month and this is an attacking track.",
            }],
        })
        match_news = {"Warriors vs Broncos": {
            "text": "- both teams conceding heavily in recent form", "accepted_count": 2,
            "warnings": [], "confidence_ceiling": "MODERATE",
        }}
        pick = generate_pick.generate_pick_for_matches(_mock_matches_with_extra_markets(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["market_type"], "total")
        self.assertEqual(pick["odds"], "1.87")
        self.assertIn("OVER", pick["selection"])
        self.assertIn("42.5", pick["selection"])

    @patch("generate_pick.anthropic.Anthropic")
    def test_spread_wrong_line_from_model_cannot_be_resolved_is_no_bet(self, mock_anthropic_cls):
        # Model names a line that doesn't match what was actually quoted --
        # must not silently resolve to the wrong price, must be treated as
        # unresolvable / dropped rather than guessing.
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "Warriors vs Broncos",
                "sport": "rugbyleague_nrl",
                "market_type": "spread",
                "selection": "Warriors",
                "line": -9.5,
                "market": "Handicap",
                "our_probability": 58,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": [],
                "reasoning": "n/a",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_matches_with_extra_markets(), {})
        self.assertFalse(pick["has_pick"])

    @patch("generate_pick.anthropic.Anthropic")
    def test_zero_news_snippets_with_general_knowledge_basis_can_still_produce_a_pick(self, mock_anthropic_cls):
        # Phase 1: zero validated news snippets should no longer force a LOW
        # confidence ceiling / NO_BET by itself -- MODERATE-confidence,
        # general-knowledge-based reasoning should be able to clear the bar.
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "market_type": "h2h",
                "selection": "France",
                "line": None,
                "market": "Head to Head",
                "our_probability": 46,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": ["no fresh news found, relying on general squad strength"],
                "reasoning": "No fresh headlines either way, but France's squad depth is a genuine edge here based on general form.",
            }],
        })
        match_news = {"France vs Spain": {
            "text": "", "accepted_count": 0,
            "warnings": ["no validated news sources — confidence capped at MODERATE (general knowledge may still apply)"],
            "confidence_ceiling": "MODERATE",
        }}
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["confidence"], "MODERATE")


class Phase2InvestorPreferenceTests(unittest.TestCase):
    """Phase 2: when multiple candidates are genuinely defensible on the same
    day, the featured pick should be biased toward Investor > Punter >
    Gambler -- but only among candidates that independently cleared the
    classifier's bar on their own merits. Never a quota, never an upgrade."""

    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_investor_grade_candidate_preferred_over_gambler_grade_same_day(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [
                # Listed FIRST but should NOT win -- Gambler-tier: long odds,
                # moderate confidence, still clears the edge bar.
                {
                    "match": "France vs Spain",
                    "sport": "soccer_fifa_world_cup",
                    "market_type": "h2h",
                    "selection": "Spain",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 40,
                    "evidence_sufficient": True,
                    "confidence": "MODERATE",
                    "uncertainty_flags": [],
                    "reasoning": "Spain at a big price have a live path through this bracket.",
                },
                # Listed SECOND but SHOULD win -- Investor-tier: short odds,
                # high confidence, clears the edge bar.
                {
                    "match": "Warriors vs Broncos",
                    "sport": "rugbyleague_nrl",
                    "market_type": "h2h",
                    "selection": "Warriors",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 65,
                    "evidence_sufficient": True,
                    "confidence": "HIGH",
                    "uncertainty_flags": [],
                    "reasoning": "Warriors are at full strength at home against a Broncos side missing several forwards.",
                },
            ],
        })
        match_news = {
            "France vs Spain": {"text": "- squad news", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"},
            "Warriors vs Broncos": {"text": "- squad news", "accepted_count": 3, "warnings": [], "confidence_ceiling": "HIGH"},
        }
        pick = generate_pick.generate_pick_for_matches(_mock_two_matches_investor_and_gambler(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["bet_type"], "INVESTOR_BET")
        self.assertEqual(pick["match"], "Warriors vs Broncos")
        # The Gambler-tier candidate genuinely existed too -- confirm it was
        # tracked as a real alternative, not silently discarded.
        self.assertEqual(pick["other_defensible_candidates"], 1)

    @patch("generate_pick.anthropic.Anthropic")
    def test_gambler_only_day_is_not_upgraded_to_investor(self, mock_anthropic_cls):
        # Only a Gambler-grade candidate exists today -- must be featured
        # as-is, never manufactured into a fake Investor pick.
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "market_type": "h2h",
                "selection": "Spain",
                "line": None,
                "market": "Head to Head",
                "our_probability": 40,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": [],
                "reasoning": "Spain at a big price have a live path through this bracket.",
            }],
        })
        match_news = {"France vs Spain": {"text": "- squad news", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"}}
        pick = generate_pick.generate_pick_for_matches(_mock_two_matches_investor_and_gambler(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["bet_type"], "GAMBLER_BET")
        self.assertEqual(pick["other_defensible_candidates"], 0)

    @patch("generate_pick.anthropic.Anthropic")
    def test_no_bet_candidate_does_not_block_a_genuinely_defensible_one(self, mock_anthropic_cls):
        # One proposed candidate has insufficient evidence (classifies as
        # NO_BET on its own), the other genuinely clears the bar -- the run
        # should still produce the real pick, not fall back to NO_BET just
        # because one of several proposals didn't hold up.
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [
                {
                    "match": "Warriors vs Broncos",
                    "sport": "rugbyleague_nrl",
                    "market_type": "h2h",
                    "selection": "Warriors",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 56,
                    "evidence_sufficient": False,
                    "confidence": "LOW",
                    "uncertainty_flags": ["thin evidence"],
                    "reasoning": "Not much to go on here.",
                },
                {
                    "match": "France vs Spain",
                    "sport": "soccer_fifa_world_cup",
                    "market_type": "h2h",
                    "selection": "Spain",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 40,
                    "evidence_sufficient": True,
                    "confidence": "MODERATE",
                    "uncertainty_flags": [],
                    "reasoning": "Spain at a big price have a live path through this bracket.",
                },
            ],
        })
        match_news = {
            "Warriors vs Broncos": {"text": "", "accepted_count": 0, "warnings": [], "confidence_ceiling": "LOW"},
            "France vs Spain": {"text": "- squad news", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"},
        }
        pick = generate_pick.generate_pick_for_matches(_mock_two_matches_investor_and_gambler(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["match"], "France vs Spain")
        self.assertEqual(pick["bet_type"], "GAMBLER_BET")

    @patch("generate_pick.anthropic.Anthropic")
    def test_all_candidates_classified_no_bet_yields_no_bet(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "Warriors vs Broncos",
                "sport": "rugbyleague_nrl",
                "market_type": "h2h",
                "selection": "Warriors",
                "line": None,
                "market": "Head to Head",
                "our_probability": 56,
                "evidence_sufficient": False,
                "confidence": "LOW",
                "uncertainty_flags": ["thin evidence"],
                "reasoning": "Not much to go on here.",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_two_matches_investor_and_gambler(), {})
        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["risk"], "NO_BET")



class Phase3ShakyEdgeRiskyNotNoBetTests(unittest.TestCase):
    """Phase 3: a candidate whose edge is below the standard bar but still
    above the shaky-angle floor should come through as a RISKY_PICK with
    honest "keep this light" caution copy, not silently become NO_BET --
    and the copy validator must still block any NO_BET-only phrasing on it
    (guards against reopening the original pick/copy contradiction bug)."""

    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_shaky_but_genuine_edge_produces_risky_pick_with_caution_copy(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        # our_probability 53 vs implied ~50 (odds 2.00) -> edge ~3.0%, below
        # the 5% standard bar but above the 2.5% shaky-angle floor.
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "market_type": "h2h",
                "selection": "France",
                "line": None,
                "market": "Head to Head",
                "our_probability": 43,
                "evidence_sufficient": True,
                "confidence": "MODERATE",
                "uncertainty_flags": ["squad rotation possible"],
                "reasoning": "It's a lighter case, but France's away form gives a genuine if shaky angle here.",
            }],
        })
        match_news = {"France vs Spain": {"text": "- squad news", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"}}
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["risk"], "RISKY_PICK")
        self.assertIsNotNone(pick["public_caution"])
        self.assertIn("keep this", pick["public_caution"].lower())
        # No NO_BET-only contradiction language leaked into the real copy.
        for text in (pick["bet_type_reason"], pick["final_explanation"]):
            self.assertNotIn("sitting this one out", text.lower())
            self.assertNotIn("no pick meets", text.lower())

    @patch("generate_pick.anthropic.Anthropic")
    def test_truly_thin_edge_below_shaky_floor_is_still_no_bet(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        # our_probability 41 vs implied 40 -> edge ~1%, below even the 2.5%
        # shaky floor -- genuinely nothing here, must remain NO_BET.
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [{
                "match": "France vs Spain",
                "sport": "soccer_fifa_world_cup",
                "market_type": "h2h",
                "selection": "France",
                "line": None,
                "market": "Head to Head",
                "our_probability": 41,
                "evidence_sufficient": True,
                "confidence": "LOW",
                "uncertainty_flags": [],
                "reasoning": "Coin flip at best, nothing genuinely defensible.",
            }],
        })
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), {})
        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["risk"], "NO_BET")

if __name__ == "__main__":
    unittest.main()
