"""
Tests for main.py's Stage 1 / Stage 2 wiring (2026-10-15 redesign). Run
#206 burned the account's entire monthly Odds API allowance by scanning
the full registry on every run; these pin down that the new pipeline (a)
never calls fetch_upcoming_odds for more than Stage 1's shortlisted
sports, (b) never calls it at all when the budget has no room or Stage 1
found nothing, and (c) records an honest content_mode/fallback_reason
distinguishing each of those cases from a real gated pick.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import fetch_odds
import quota_budget
import run_status

SAMPLE_MATCH = {
    "sport": "rugbyleague_nrl",
    "sport_label": "NRL",
    "match": "Warriors vs Storm",
    "home_team": "Warriors",
    "away_team": "Storm",
    "kickoff": "2026-10-20T08:00:00Z",
}

GATED_PICK = {
    "has_pick": True,
    "match": SAMPLE_MATCH["match"],
    "selection": "Warriors to Win",
    "odds": "1.80",
    "market": "Head to Head",
    "sport_label": "NRL",
    "bet_type": "INVESTOR_BET",
    "risk": "STANDARD_PICK",
    "confidence": "HIGH",
    "final_explanation": "Clean edge here.",
    "research_warnings": [],
}

RESEARCH_RECORD_NRL_SELECTED = {"selected_sport_keys": ["rugbyleague_nrl"], "candidates": [], "warnings": []}
RESEARCH_RECORD_NONE_SELECTED = {"selected_sport_keys": [], "candidates": [], "warnings": []}


def _candidate_with_fresh_anchor():
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return {
        "fixture_id": "warriors-vs-storm", "sport_key": None, "sport_name": "NRL",
        "participants": ["Warriors", "Storm"],
        "kickoff_utc": (now + timedelta(hours=6)).isoformat(),
        "proposed_selection": "Warriors", "market_type": "h2h",
        "research_reason": "Warriors have won 4 of their last 5 home games.",
        "uncertainty_flags": [],
        "market_anchor": {
            "source": "Example Books", "favourite": "Warriors", "selection": "Warriors",
            "market": "h2h", "line": None, "price": 1.9,
            "observed_at_utc": (now - timedelta(minutes=5)).isoformat(),
            "url": "https://example.com/odds",
        },
    }


class TwoStagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR)
        pm_main.LATEST_RUN_PATH = os.path.join(self.tmp, "data", "latest_run.json")
        pm_main.CARDS_DIR = os.path.join(self.tmp, "data", "cards")
        self._orig_budget_path = quota_budget.BUDGET_PATH
        quota_budget.BUDGET_PATH = os.path.join(self.tmp, "quota_budget.json")

    def tearDown(self):
        pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR = self._orig
        quota_budget.BUDGET_PATH = self._orig_budget_path
        fetch_odds.LAST_FETCH_ERRORS = []
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fund_period(self, remaining=500):
        quota_budget.start_new_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC,
                                       confirmed_provider_remaining=remaining)

    # ---- the core quota-exhaustion protection ----

    def test_exhausted_budget_never_calls_fetch_upcoming_odds(self):
        quota_budget.init_exhausted_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC)
        with patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED)), \
             patch("fetch_odds.fetch_upcoming_odds") as mock_fetch:
            pm_main.run()
            mock_fetch.assert_not_called()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["fallback_reason"], run_status.FALLBACK_QUOTA_EXHAUSTED)
        self.assertEqual(saved["content_mode"], run_status.MODE_STATUS_ONLY)
        self.assertFalse(saved["pick"]["has_pick"])

    def test_no_sport_selected_never_calls_fetch_upcoming_odds(self):
        self._fund_period()
        with patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NONE_SELECTED)), \
             patch("fetch_odds.fetch_upcoming_odds") as mock_fetch:
            pm_main.run()
            mock_fetch.assert_not_called()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["fallback_reason"], run_status.FALLBACK_NO_SPORT_SELECTED)
        self.assertEqual(saved["content_mode"], run_status.MODE_NO_BET)

    def test_only_the_shortlisted_sports_are_ever_queried(self):
        self._fund_period()
        record = {"selected_sport_keys": ["rugbyleague_nrl", "mma_mixed_martial_arts"], "candidates": [], "warnings": []}
        with patch("research_shortlist.run_research_shortlist", return_value=record), \
             patch("fetch_odds.fetch_upcoming_odds", return_value=[]) as mock_fetch:
            pm_main.run()
            mock_fetch.assert_called_once_with(["rugbyleague_nrl", "mma_mixed_martial_arts"], hours_ahead=24)

    def test_successful_reservation_is_confirmed_in_the_real_budget_store(self):
        self._fund_period()
        with patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED)), \
             patch("fetch_odds.fetch_upcoming_odds", return_value=[]):
            pm_main.run()

        rec = quota_budget.get_period(quota_budget.CURRENT_PERIOD_KEY)
        self.assertEqual(rec["buckets"][quota_budget.ODDS]["charged"], fetch_odds.sport_credit_cost("rugbyleague_nrl"))
        self.assertEqual(rec["buckets"][quota_budget.ODDS]["reserved_total"], 0)

    # ---- content_mode on a real gated pick ----

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_gated_pick_sets_content_mode_and_no_fallback_reason(self, _odds, _news, _research):
        self._fund_period()
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(GATED_PICK)), \
             patch.object(pm_main, "render_card", return_value={"ok": True, "files": {}}):
            pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["content_mode"], run_status.MODE_GATED_PICK)
        self.assertIsNone(saved["fallback_reason"])

    # ---- research lead on a no-bet day ----

    def test_research_lead_surfaces_when_a_verified_candidate_exists_but_cannot_be_gated(self):
        self._fund_period()
        record = {"selected_sport_keys": [], "candidates": [_candidate_with_fresh_anchor()], "warnings": []}
        with patch("research_shortlist.run_research_shortlist", return_value=record), \
             patch("fetch_odds.fetch_upcoming_odds") as mock_fetch:
            pm_main.run()
            mock_fetch.assert_not_called()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["content_mode"], run_status.MODE_RESEARCH_ONLY)
        self.assertIsNotNone(saved["research_lead"])
        self.assertEqual(saved["research_lead"]["match"], "Warriors vs Storm")
        # Never a gated-path claim on a research lead.
        for field in ("our_probability", "implied_probability", "edge_pct", "risk", "bet_type"):
            self.assertIsNone(saved["research_lead"][field])

    def test_no_research_lead_when_no_candidate_has_a_usable_anchor(self):
        self._fund_period()
        stale_candidate = _candidate_with_fresh_anchor()
        stale_candidate["market_anchor"] = None
        record = {"selected_sport_keys": [], "candidates": [stale_candidate], "warnings": []}
        with patch("research_shortlist.run_research_shortlist", return_value=record):
            pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertIsNone(saved["research_lead"])
        self.assertEqual(saved["content_mode"], run_status.MODE_NO_BET)


if __name__ == "__main__":
    unittest.main()
