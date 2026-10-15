"""
Tests for generate_pick.build_research_only_pick (2026-10-15 redesign,
Section 7). This builder must refuse anything that isn't a genuinely
fresh, verified public market anchor on a fixture that hasn't started --
and must never let a probability/edge/bet_type/risk claim sneak into the
result, since RESEARCH_ONLY content is explicitly not gate-approved.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_pick import build_research_only_pick

NOW = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)


def _candidate(**overrides):
    base = {
        "fixture_id": "team-a-vs-team-b",
        "sport_key": "rugbyleague_nrl",
        "sport_name": "NRL",
        "participants": ["Team A", "Team B"],
        "kickoff_utc": (NOW + timedelta(hours=6)).isoformat(),
        "proposed_selection": "Team A",
        "market_type": "h2h",
        "research_reason": "Team A has won 4 of the last 5 meetings at home.",
        "uncertainty_flags": [],
        "market_anchor": {
            "source": "Example Books", "favourite": "Team A", "selection": "Team A",
            "market": "h2h", "line": None, "price": 1.8,
            "observed_at_utc": (NOW - timedelta(minutes=10)).isoformat(),
            "url": "https://example.com/odds",
        },
    }
    base.update(overrides)
    return base


class BuildResearchOnlyPickTests(unittest.TestCase):
    def test_valid_candidate_produces_a_research_only_pick(self):
        pick = build_research_only_pick(_candidate(), now_utc=NOW)
        self.assertIsNotNone(pick)
        self.assertTrue(pick["has_pick"])
        self.assertEqual(pick["content_mode"], "RESEARCH_ONLY")
        self.assertEqual(pick["match"], "Team A vs Team B")
        self.assertEqual(pick["odds"], 1.8)

    def test_never_carries_a_probability_edge_or_tier_claim(self):
        pick = build_research_only_pick(_candidate(), now_utc=NOW)
        for field in ("our_probability", "implied_probability", "edge_pct", "risk", "bet_type"):
            self.assertIsNone(pick[field])

    def test_carries_the_fields_the_public_copy_builders_require(self):
        # build_telegram_text/build_instagram_caption index these directly
        # -- missing them would KeyError, not degrade gracefully.
        pick = build_research_only_pick(_candidate(), now_utc=NOW)
        self.assertIn("NOT A GATED PICK", pick["bet_type_label"])
        self.assertTrue(pick["bet_type_reason"])

    def test_missing_anchor_returns_none(self):
        self.assertIsNone(build_research_only_pick(_candidate(market_anchor=None), now_utc=NOW))

    def test_non_https_anchor_url_returns_none(self):
        c = _candidate()
        c["market_anchor"]["url"] = "http://example.com/odds"
        self.assertIsNone(build_research_only_pick(c, now_utc=NOW))

    def test_stale_anchor_returns_none(self):
        c = _candidate()
        c["market_anchor"]["observed_at_utc"] = (NOW - timedelta(hours=2)).isoformat()
        self.assertIsNone(build_research_only_pick(c, now_utc=NOW))

    def test_anchor_just_under_the_age_limit_is_accepted(self):
        c = _candidate()
        c["market_anchor"]["observed_at_utc"] = (NOW - timedelta(minutes=59)).isoformat()
        self.assertIsNotNone(build_research_only_pick(c, now_utc=NOW))

    def test_fixture_already_started_returns_none(self):
        c = _candidate(kickoff_utc=(NOW - timedelta(minutes=5)).isoformat())
        self.assertIsNone(build_research_only_pick(c, now_utc=NOW))

    def test_non_numeric_price_returns_none(self):
        c = _candidate()
        c["market_anchor"]["price"] = "not a number"
        self.assertIsNone(build_research_only_pick(c, now_utc=NOW))

    def test_price_of_one_or_less_returns_none(self):
        c = _candidate()
        c["market_anchor"]["price"] = 1.0
        self.assertIsNone(build_research_only_pick(c, now_utc=NOW))


if __name__ == "__main__":
    unittest.main()
