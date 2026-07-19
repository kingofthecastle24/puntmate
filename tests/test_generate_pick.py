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
    def test_priority_sport_preferred_over_higher_bet_type_tier_in_fallback_sport(self, mock_anthropic_cls):
        """2026-07-18 (Micah): NRL/Rugby/MMA/World Cup are prioritised over
        fallback sports (MLB etc) even when the fallback candidate is a
        stronger bet-type tier -- same mechanism/strength as owner-focus
        fixtures. Both candidates here genuinely cleared the bar; this only
        tests which one gets featured."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({
            "candidates": [
                # Investor-tier (short odds, high confidence) but MLB --
                # a fallback sport -- should NOT win despite the stronger tier.
                {
                    "match": "Yankees vs Red Sox",
                    "sport": "baseball_mlb",
                    "market_type": "h2h",
                    "selection": "Yankees",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 65,
                    "evidence_sufficient": True,
                    "confidence": "HIGH",
                    "uncertainty_flags": [],
                    "reasoning": "Yankees are the clearly stronger side at home.",
                },
                # Gambler-tier (long odds) but NRL -- a priority sport --
                # SHOULD win despite the weaker tier.
                {
                    "match": "Warriors vs Broncos",
                    "sport": "rugbyleague_nrl",
                    "market_type": "h2h",
                    "selection": "Broncos",
                    "line": None,
                    "market": "Head to Head",
                    "our_probability": 40,
                    "evidence_sufficient": True,
                    "confidence": "MODERATE",
                    "uncertainty_flags": [],
                    "reasoning": "Broncos at a big price have a live path to the upset.",
                },
            ],
        })
        matches = [
            {
                "sport": "baseball_mlb", "match": "Yankees vs Red Sox",
                "home_team": "Yankees", "away_team": "Red Sox",
                "kickoff": "2026-07-19T00:00:00Z",
                "odds": {"home": 1.55, "away": 2.50, "draw": None},
                "implied_probs": {"home": 0.617, "away": 0.383, "draw": 0},
                "big_game": False,
            },
            {
                "sport": "rugbyleague_nrl", "match": "Warriors vs Broncos",
                "home_team": "Warriors", "away_team": "Broncos",
                "kickoff": "2026-07-19T08:00:00Z",
                "odds": {"home": 1.50, "away": 3.20, "draw": None},
                "implied_probs": {"home": 0.68, "away": 0.32, "draw": 0},
                "big_game": False,
            },
        ]
        match_news = {
            "Yankees vs Red Sox": {"text": "- form", "accepted_count": 2, "warnings": [], "confidence_ceiling": "HIGH"},
            "Warriors vs Broncos": {"text": "- form", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"},
        }
        pick = generate_pick.generate_pick_for_matches(matches, match_news)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["match"], "Warriors vs Broncos")
        self.assertEqual(pick["sport"], "rugbyleague_nrl")
        # The MLB candidate genuinely existed too -- tracked, not discarded.
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


class IncidentUncertaintyFlagLeakTests(unittest.TestCase):
    """Regression coverage for TWO real incidents in the same mechanism,
    both proven by live production data, not hypothetical:

    Incident #1 (2026-07-17): a live Telegram post shipped with 'Worth
    knowing: Warriors news snippet references Cowboys not Dragons — possible
    copy-paste from different week; Dragons form unknown beyond general
    knowledge.' — internal research commentary leaked into public copy via
    uncertainty_flags.

    Incident #2 (2026-07-19, real dry run, Spain v Argentina): a prompt-only
    fix telling the model never to argue the opposite side of its own pick
    in an uncertainty_flag was added after incident #1's pattern recurred in
    a different form — and the very next real generation still did it:
    reasoning backed UNDER 2.5, then 'Worth knowing: World Cup final
    pressure can produce nervy, open-ended attacks from both sides late on;
    Argentina's attacking firepower with Messi-era players capable of
    blowing games open' shipped right after it, undercutting the pick.

    Both incidents share one root cause: uncertainty_flags reaching public
    copy at all is inherently risky, since neither a leak-detector nor a
    contradiction-detector can be trusted to catch every generative
    phrasing. The fix is structural, not another filter: uncertainty_flags
    NEVER reach public copy any more, full stop — they always go to
    research_warnings (internal-only, visible in the Gmail preview and
    post-metadata.json)."""

    def test_uncertainty_flags_never_appear_in_public_text_regardless_of_content(self):
        research_warnings = []
        text = generate_pick.build_final_explanation(
            "The market has Warriors at 83% but honestly this feels light.",
            "RISKY_PICK",
            ["Warriors news snippet references Cowboys not Dragons — possible copy-paste from different week",
             "Dragons form unknown beyond general knowledge"],
            research_warnings,
        )
        self.assertNotIn("news snippet", text.lower())
        self.assertNotIn("copy-paste", text.lower())
        self.assertNotIn("beyond general knowledge", text.lower())
        self.assertNotIn("Worth knowing", text)
        self.assertEqual(len(research_warnings), 2)

    def test_even_a_genuine_looking_flag_is_diverted_not_published(self):
        """A flag that reads as a perfectly legitimate punter-facing caveat
        ('star fullback is a late fitness doubt') still must not reach
        public copy — the 2026-07-19 incident proves even 'safe-sounding'
        flags can undercut the pick, so there is no longer any category of
        uncertainty_flag that is allowed into public text."""
        research_warnings = []
        text = generate_pick.build_final_explanation(
            "Solid touch here, the numbers back it.",
            "RISKY_PICK",
            ["star fullback is a late fitness doubt"],
            research_warnings,
        )
        self.assertNotIn("Worth knowing", text)
        self.assertNotIn("fullback", text)
        self.assertEqual(text, "Solid touch here, the numbers back it.")
        self.assertTrue(any("fullback" in w for w in research_warnings))

    def test_real_spain_argentina_contradiction_never_reaches_public_copy(self):
        """Regression test using the exact real copy from the 2026-07-19
        dry run Micah triggered himself — this is the flag that shipped and
        shouldn't have."""
        research_warnings = []
        reasoning = (
            "World Cup finals are historically low-scoring; the average "
            "goals in finals since 1990 is well under 2.5. Spain under Luis "
            "de la Fuente are a possession-heavy side that slows the game "
            "down and suffocates opponents, and Argentina's defensive "
            "structure is disciplined."
        )
        flag = (
            "World Cup final pressure can produce nervy, open-ended attacks "
            "from both sides late on; Argentina's attacking firepower with "
            "Messi-era players capable of blowing games open."
        )
        text = generate_pick.build_final_explanation(reasoning, "RISKY_PICK", [flag], research_warnings)
        self.assertNotIn("Worth knowing", text)
        self.assertNotIn("blowing games open", text)
        self.assertNotIn("open-ended attacks", text)
        self.assertEqual(text, reasoning.strip())
        self.assertTrue(any("blowing games open" in w for w in research_warnings))

    def test_no_research_warnings_list_provided_still_never_leaks(self):
        """If callers don't pass a research_warnings list, flags are simply
        dropped — never silently appended to public text as a fallback."""
        text = generate_pick.build_final_explanation(
            "Solid touch here.", "RISKY_PICK", ["wet weather forecast for kickoff"],
        )
        self.assertEqual(text, "Solid touch here.")

    @patch("generate_pick.anthropic.Anthropic")
    def test_end_to_end_leaked_incident_phrase_never_reaches_final_explanation(self, mock_anthropic_cls):
        """Full generate_pick_for_matches path with a mocked Claude response
        that reproduces the exact incident #1 candidate — proves the
        pipeline as a whole (not just the helper function in isolation) no
        longer lets this through, and still produces a usable pick rather
        than failing the whole run."""
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
                "our_probability": 43,
                "evidence_sufficient": True,
                "confidence": "HIGH",
                "uncertainty_flags": [
                    "Warriors news snippet references Cowboys not Dragons — possible copy-paste from different week",
                    "Dragons form unknown beyond general knowledge",
                ],
                "reasoning": "France's away record and Spain's missing regulars make this a genuine, if shaky, angle.",
            }],
        })
        match_news = {"France vs Spain": {"text": "- squad news", "accepted_count": 2, "warnings": [], "confidence_ceiling": "MODERATE"}}
        pick = generate_pick.generate_pick_for_matches(_mock_matches(), match_news)
        self.assertTrue(pick["has_pick"])
        for text in (pick["bet_type_reason"], pick["final_explanation"]):
            self.assertNotIn("news snippet", text.lower())
            self.assertNotIn("copy-paste", text.lower())
            self.assertNotIn("beyond general knowledge", text.lower())
            self.assertNotIn("Worth knowing", text)
        self.assertTrue(any("news snippet" in w or "beyond general knowledge" in w for w in pick["research_warnings"]))


class TruncatedModelResponseFailSafeTests(unittest.TestCase):
    """Run #49 (2026-07-17) crashed with JSONDecodeError when a 59-fixture
    slate pushed Claude's candidates array past max_tokens and the JSON came
    back truncated. Unparseable model output must degrade to NO_BET, never
    crash the run."""

    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_truncated_json_fails_safe_to_no_bet(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        response = MagicMock()
        response.content = [MagicMock(text='{"candidates": [{"match": "France vs Spain", "sport": "soccer_fifa_world_cup", "market_type": "h2h", "selection": "Fran')]
        response.stop_reason = "max_tokens"
        mock_client.messages.create.return_value = response

        pick = generate_pick.generate_pick_for_matches(_mock_matches(), {})
        self.assertFalse(pick["has_pick"])
        self.assertEqual(pick["risk"], "NO_BET")
        self.assertTrue(any("could not be parsed" in w for w in pick["research_warnings"]))

    @patch("generate_pick.anthropic.Anthropic")
    def test_oversized_slate_is_capped_before_prompting(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": [], "reasoning": "nothing today"})

        base = _mock_matches()[0]
        many = []
        for i in range(40):
            m = dict(base)
            m["match"] = f"Team{i} vs Team{i+100}"
            m["home_team"], m["away_team"] = f"Team{i}", f"Team{i+100}"
            many.append(m)
        pick = generate_pick.generate_pick_for_matches(many, {})
        prompt_sent = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Team0 vs Team100", prompt_sent)
        self.assertNotIn("Team39 vs Team139", prompt_sent)
        self.assertTrue(any("only the first" in w for w in pick["research_warnings"]))

    @patch("generate_pick.anthropic.Anthropic")
    def test_multi_is_not_capped_at_three_legs(self, mock_anthropic_cls):
        """2026-07-18 (Micah): a multi can be as long as the genuine
        candidates support -- 6, 8, whatever clears the bar on distinct
        matches. This was previously hard-capped at exactly 3 legs; this
        test locks in that six independently-clearing candidates produce
        a six-leg multi, not a truncated three-leg one."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        matches = []
        candidates = []
        for i in range(6):
            m = {
                "sport": "rugbyleague_nrl",
                "match": f"Team{i}A vs Team{i}B",
                "home_team": f"Team{i}A", "away_team": f"Team{i}B",
                "kickoff": "2026-07-19T06:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            }
            matches.append(m)
            candidates.append({
                "match": m["match"], "sport": "rugbyleague_nrl", "market_type": "h2h",
                "selection": f"Team{i}A", "line": None, "market": "Head to Head",
                "our_probability": 68, "evidence_sufficient": True, "confidence": "MODERATE",
                "uncertainty_flags": [], "reasoning": "Genuine, independent edge on its own merits.",
            })
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": candidates})

        news = {m["match"]: {"confidence_ceiling": "MODERATE"} for m in matches}
        pick = generate_pick.generate_pick_for_matches(matches, news, build_multis=True)

        self.assertTrue(pick["has_pick"])
        self.assertEqual(len(pick["punter_multi_legs"]), 6)
        self.assertEqual(
            {leg["match"] for leg in pick["punter_multi_legs"]},
            {m["match"] for m in matches},
        )
        # All 6 legs are rugbyleague_nrl -> should hint at the TAB
        # AFL/Rugby-codes 4+ leg promo category.
        self.assertIsNotNone(pick["punter_multi_promo_hint"])
        self.assertIn("rugby codes", pick["punter_multi_promo_hint"])
        self.assertEqual(pick["gambler_multi_legs"], [])

    @patch("generate_pick.anthropic.Anthropic")
    def test_multi_promo_hint_none_when_legs_are_mixed_sports(self, mock_anthropic_cls):
        """A 3-leg multi mixing NRL + MLB doesn't sit entirely within any
        single TAB promo category, so no hint should be attached (never
        guess/half-match — either it cleanly qualifies or it doesn't)."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        matches = [
            {
                "sport": "rugbyleague_nrl", "match": "Team1A vs Team1B",
                "home_team": "Team1A", "away_team": "Team1B",
                "kickoff": "2026-07-19T06:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            },
            {
                "sport": "rugbyleague_nrl", "match": "Team2A vs Team2B",
                "home_team": "Team2A", "away_team": "Team2B",
                "kickoff": "2026-07-19T18:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            },
            {
                "sport": "baseball_mlb", "match": "Team3A vs Team3B",
                "home_team": "Team3A", "away_team": "Team3B",
                "kickoff": "2026-07-19T19:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            },
            {
                "sport": "baseball_mlb", "match": "Team4A vs Team4B",
                "home_team": "Team4A", "away_team": "Team4B",
                "kickoff": "2026-07-19T20:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            },
        ]
        candidates = [{
            "match": m["match"], "sport": m["sport"], "market_type": "h2h",
            "selection": m["home_team"], "line": None, "market": "Head to Head",
            "our_probability": 68, "evidence_sufficient": True, "confidence": "MODERATE",
            "uncertainty_flags": [], "reasoning": "Genuine, independent edge on its own merits.",
        } for m in matches]
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": candidates})

        news = {m["match"]: {"confidence_ceiling": "MODERATE"} for m in matches}
        pick = generate_pick.generate_pick_for_matches(matches, news, build_multis=True)

        self.assertEqual(len(pick["punter_multi_legs"]), 4)
        self.assertIsNone(pick["punter_multi_promo_hint"])


class DailyRunNeverBuildsMultisTests(unittest.TestCase):
    """2026-07-19 (Micah): 'I don't want the gambler/degen multi to run
    everyday because it might ruin the strike rate and reputation.' Multis
    are now exclusively a weekend-pool feature (generate_weekend_multi.py)
    -- the ordinary daily call (build_multis defaults to False) must NEVER
    produce multi legs, even when the day's fixtures would otherwise easily
    clear the 3-leg bar for one or both tiers."""

    def setUp(self):
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

    @patch("generate_pick.anthropic.Anthropic")
    def test_default_call_returns_no_multis_even_with_six_qualifying_legs(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        matches, candidates = [], []
        for i in range(6):
            m = {
                "sport": "rugbyleague_nrl", "match": f"Team{i}A vs Team{i}B",
                "home_team": f"Team{i}A", "away_team": f"Team{i}B",
                "kickoff": "2026-07-19T06:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            }
            matches.append(m)
            candidates.append({
                "match": m["match"], "sport": "rugbyleague_nrl", "market_type": "h2h",
                "selection": f"Team{i}A", "line": None, "market": "Head to Head",
                "our_probability": 68, "evidence_sufficient": True, "confidence": "MODERATE",
                "uncertainty_flags": [], "reasoning": "Genuine, independent edge on its own merits.",
            })
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": candidates})
        news = {m["match"]: {"confidence_ceiling": "MODERATE"} for m in matches}

        # No build_multis kwarg at all -- exactly how main.py's daily run calls this.
        pick = generate_pick.generate_pick_for_matches(matches, news)

        self.assertTrue(pick["has_pick"])  # the featured single pick is unaffected
        self.assertEqual(pick["punter_multi_legs"], [])
        self.assertEqual(pick["gambler_multi_legs"], [])
        self.assertIsNone(pick["punter_multi_promo_hint"])
        self.assertIsNone(pick["gambler_multi_promo_hint"])


class TwoTierMultiSplitTests(unittest.TestCase):
    """2026-07-19 (Micah): the multi is now two independent tiers keyed off
    bet_type — Punter Multi (INVESTOR_BET/PUNTER_BET) and Gambler/Degenerate
    Multi (GAMBLER_BET). A candidate can only ever land in exactly one tier,
    and each tier independently needs 3+ legs to fire."""

    @patch("generate_pick.anthropic.Anthropic")
    def test_gambler_tier_candidates_land_in_gambler_multi_only(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        matches, candidates = [], []
        for i in range(3):
            m = {
                "sport": "mma_mixed_martial_arts",
                "match": f"Fighter{i}A vs Fighter{i}B",
                "home_team": f"Fighter{i}A", "away_team": f"Fighter{i}B",
                "kickoff": "2026-07-19T06:00:00Z",
                # Long-priced underdog -> GAMBLER_BET (odds >= GAMBLER_ODDS_MIN).
                "odds": {"home": 3.20, "away": 1.35, "draw": None},
                "implied_probs": {"home": 0.30, "away": 0.70, "draw": 0},
                "big_game": False,
            }
            matches.append(m)
            candidates.append({
                "match": m["match"], "sport": "mma_mixed_martial_arts", "market_type": "h2h",
                "selection": f"Fighter{i}A", "line": None, "market": "Head to Head",
                "our_probability": 45, "evidence_sufficient": True, "confidence": "MODERATE",
                "uncertainty_flags": [], "reasoning": "Genuine, independent longshot edge.",
            })
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": candidates})
        news = {m["match"]: {"confidence_ceiling": "MODERATE"} for m in matches}
        pick = generate_pick.generate_pick_for_matches(matches, news, build_multis=True)

        self.assertEqual(len(pick["gambler_multi_legs"]), 3)
        self.assertEqual(pick["punter_multi_legs"], [])

    @patch("generate_pick.anthropic.Anthropic")
    def test_fewer_than_three_in_one_tier_produces_no_multi_for_that_tier_only(self, mock_anthropic_cls):
        """4 measured (Punter-tier) candidates + only 2 longshot (Gambler-
        tier) candidates -> Punter Multi fires, Gambler Multi does not.
        Tiers are independent; a shortfall in one never blocks the other."""
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        matches, candidates = [], []
        for i in range(4):
            m = {
                "sport": "rugbyleague_nrl", "match": f"NRL{i}A vs NRL{i}B",
                "home_team": f"NRL{i}A", "away_team": f"NRL{i}B",
                "kickoff": "2026-07-19T06:00:00Z",
                "odds": {"home": 1.60, "away": 2.30, "draw": None},
                "implied_probs": {"home": 0.59, "away": 0.41, "draw": 0},
                "big_game": False,
            }
            matches.append(m)
            candidates.append({
                "match": m["match"], "sport": "rugbyleague_nrl", "market_type": "h2h",
                "selection": f"NRL{i}A", "line": None, "market": "Head to Head",
                "our_probability": 68, "evidence_sufficient": True, "confidence": "MODERATE",
                "uncertainty_flags": [], "reasoning": "Genuine, independent edge on its own merits.",
            })
        for i in range(2):
            m = {
                "sport": "mma_mixed_martial_arts", "match": f"MMA{i}A vs MMA{i}B",
                "home_team": f"MMA{i}A", "away_team": f"MMA{i}B",
                "kickoff": "2026-07-19T08:00:00Z",
                "odds": {"home": 3.20, "away": 1.35, "draw": None},
                "implied_probs": {"home": 0.30, "away": 0.70, "draw": 0},
                "big_game": False,
            }
            matches.append(m)
            candidates.append({
                "match": m["match"], "sport": "mma_mixed_martial_arts", "market_type": "h2h",
                "selection": f"MMA{i}A", "line": None, "market": "Head to Head",
                "our_probability": 45, "evidence_sufficient": True, "confidence": "MODERATE",
                "uncertainty_flags": [], "reasoning": "Genuine, independent longshot edge.",
            })
        mock_client.messages.create.return_value = _mock_anthropic_response({"candidates": candidates})
        news = {m["match"]: {"confidence_ceiling": "MODERATE"} for m in matches}
        pick = generate_pick.generate_pick_for_matches(matches, news, build_multis=True)

        self.assertEqual(len(pick["punter_multi_legs"]), 4)
        self.assertEqual(pick["gambler_multi_legs"], [])  # only 2 -> below the 3-leg floor


class SystemPromptQualityGuardrailTests(unittest.TestCase):
    """2026-07-19 (Micah): pick explanations were reading as generic filler
    ('mid-season games between finals hopefuls can be cagey') instead of a
    concrete case for the specific teams, and uncertainty_flags were
    directly arguing the opposite side of the pick right after the
    reasoning made its case (e.g. backing UNDER then flagging 'this could
    be high-scoring'). Fixed in the prompt, not in deterministic code —
    these tests just guard against the instruction silently regressing;
    they cannot verify actual model output (no live model access in this
    sandbox), so a real run is the only way to confirm the copy actually
    reads better."""

    def test_prompt_demands_concrete_not_generic_reasoning(self):
        self.assertIn("SPECIFIC, CONCRETE case", generate_pick.SYSTEM_PROMPT)
        self.assertIn("genre filler", generate_pick.SYSTEM_PROMPT)

    def test_prompt_forbids_uncertainty_flags_arguing_the_opposite_side(self):
        self.assertIn("must NEVER argue the opposite side", generate_pick.SYSTEM_PROMPT)
        self.assertIn("France v England", generate_pick.SYSTEM_PROMPT)


class TruncationRegressionTests(unittest.TestCase):
    """BUG (reported 2026-07-18 by Micah, France vs England / FIFA World
    Cup / UNDER 3.5 / PUNTER — a real live post, not hypothetical): the
    Telegram post read '...Getting four or… Worth knowing: ...' — the main
    reasoning sentence was hard-cut at a fixed 160-char length before the
    uncertainty-flag caveat was appended, slicing the thought off
    mid-sentence with no natural break. Root cause was
    generate_pick._one_sentence()'s naive character truncation. Fixed by
    routing through text_format.truncate_at_sentence, which only cuts at a
    complete sentence boundary (or, failing that, a whole-word boundary)."""

    def test_long_reasoning_is_not_cut_mid_sentence(self):
        """Also doubles as a regression guard that uncertainty_flags (like
        the one below, which itself argues the opposite side of the pick)
        never reach the public final_explanation at all any more — see
        IncidentUncertaintyFlagLeakTests for the dedicated coverage of that
        fix."""
        raw_reasoning = (
            "This is a third-place playoff — teams are emotionally drained, "
            "motivations are mixed, and sides in these situations often play "
            "conservatively. Getting four or more goals in a dead rubber like "
            "this is unlikely given how both sides typically approach these "
            "fixtures."
        )
        reasoning_sentence = generate_pick._one_sentence(
            generate_pick.sanitize_reasoning(raw_reasoning)
        )
        research_warnings = []
        final = generate_pick.build_final_explanation(
            reasoning_sentence,
            "RISKY_PICK",
            ["third-place playoffs can occasionally produce high-scoring "
             "open games; both teams have attacking quality that can click "
             "on the day"],
            research_warnings,
        )

        self.assertNotIn("Getting four or…", final)
        self.assertNotIn("or… Worth knowing", final)
        self.assertIn("Getting four or more goals in a dead rubber like this "
                      "is unlikely given how both sides typically approach "
                      "these fixtures.", final)
        self.assertNotIn("Worth knowing:", final)
        self.assertTrue(any("high-scoring" in w for w in research_warnings))

    def test_one_sentence_leaves_short_reasoning_untouched(self):
        text = "Warriors have won four straight at home."
        self.assertEqual(generate_pick._one_sentence(text), text)

    def test_one_sentence_only_truncates_pathological_run_ons(self):
        run_on = "word " * 200
        result = generate_pick._one_sentence(run_on.strip(), max_len=50)
        self.assertLessEqual(len(result), 52)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn("wor…", result)


if __name__ == "__main__":
    unittest.main()
