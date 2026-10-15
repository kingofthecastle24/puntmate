"""
Tests for generate_weekend_multi.py — the weekend-pool Punter/Gambler-
Degenerate multi pipeline (2026-07-19, Micah). 2026-10-15 redesign: this
job now runs Stage 1 (research_shortlist.py) before any paid odds call,
exactly like main.py -- these tests mock that call and fund a budget
period so the rest of the existing multi-assembly behaviour is still
exercised end to end.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_weekend_multi as gwm
import quota_budget

WEEKEND_MATCHES = [
    {"match": f"Team{i}A vs Team{i}B", "sport_label": "NRL", "sport": "rugbyleague_nrl",
     "kickoff": "2026-07-19T06:00:00Z"}
    for i in range(4)
]

WEEKEND_PICK_RESULT = {
    "has_pick": True,
    "match": "Team0A vs Team0B",
    "punter_multi_legs": [
        {"match": f"Team{i}A vs Team{i}B", "sport_label": "NRL", "selection": f"Team{i}A", "market": "Head to Head", "odds": "1.70"}
        for i in range(3)
    ],
    "punter_multi_promo_hint": None,
    "gambler_multi_legs": [],
    "gambler_multi_promo_hint": None,
    "research_warnings": [],
}

RESEARCH_RECORD_NRL_SELECTED = {"selected_sport_keys": ["rugbyleague_nrl"], "candidates": [], "warnings": []}
RESEARCH_RECORD_NONE_SELECTED = {"selected_sport_keys": [], "candidates": [], "warnings": []}


class GenerateWeekendMultiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (gwm.REPO_ROOT, gwm.LATEST_WEEKEND_RUN_PATH, gwm.CARDS_DIR)
        gwm.REPO_ROOT = self.tmp
        gwm.LATEST_WEEKEND_RUN_PATH = os.path.join(self.tmp, "data", "latest_weekend_run.json")
        gwm.CARDS_DIR = os.path.join(self.tmp, "data", "cards")
        self._orig_budget_path = quota_budget.BUDGET_PATH
        quota_budget.BUDGET_PATH = os.path.join(self.tmp, "quota_budget.json")

    def tearDown(self):
        gwm.REPO_ROOT, gwm.LATEST_WEEKEND_RUN_PATH, gwm.CARDS_DIR = self._orig
        quota_budget.BUDGET_PATH = self._orig_budget_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fund_period(self, remaining=500):
        quota_budget.start_new_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC,
                                       confirmed_provider_remaining=remaining)

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_wide_window_is_requested_and_multis_saved(self, mock_fetch, *_mocks):
        self._fund_period()
        mock_fetch.return_value = WEEKEND_MATCHES
        gwm.run()

        mock_fetch.assert_called_once_with(["rugbyleague_nrl"], hours_ahead=gwm.WEEKEND_HOURS_AHEAD)
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(len(saved["punter_multi_legs"]), 3)
        self.assertEqual(saved["gambler_multi_legs"], [])
        self.assertEqual(saved["hours_ahead"], gwm.WEEKEND_HOURS_AHEAD)

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_build_multis_true_is_passed_through(self, mock_fetch, *_mocks):
        self._fund_period()
        mock_fetch.return_value = WEEKEND_MATCHES
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT)) as mock_gen:
            gwm.run()
        mock_gen.assert_called_once()
        self.assertTrue(mock_gen.call_args.kwargs.get("build_multis"))

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_only_qualifying_tier_gets_rendered(self, mock_fetch, _fetch_news, _gen, mock_render, _research):
        self._fund_period()
        mock_fetch.return_value = WEEKEND_MATCHES
        gwm.run()
        # Punter cleared 3 legs -> rendered; Gambler is empty -> never rendered.
        rendered_tiers = [call.args[1] for call in mock_render.call_args_list]
        self.assertIn("punter", rendered_tiers)
        self.assertNotIn("gambler", rendered_tiers)

    def test_no_sport_selected_stays_silent_and_never_calls_fetch_odds(self):
        with patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NONE_SELECTED)), \
             patch("fetch_odds.fetch_upcoming_odds") as mock_fetch:
            gwm.run()
            mock_fetch.assert_not_called()
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["punter_multi_legs"], [])
        self.assertEqual(saved["gambler_multi_legs"], [])
        self.assertEqual(saved["fixture_count"], 0)
        self.assertEqual(saved["fallback_reason"], "no_sport_selected")

    def test_exhausted_budget_never_calls_fetch_upcoming_odds(self):
        quota_budget.init_exhausted_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC)
        with patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED)), \
             patch("fetch_odds.fetch_upcoming_odds") as mock_fetch:
            gwm.run()
            mock_fetch.assert_not_called()
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["fallback_reason"], "quota_exhausted")

    def test_research_leads_surfaced_on_a_quiet_weekend_with_a_verified_candidate(self):
        self._fund_period()
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        candidate = {
            "fixture_id": "x", "sport_key": None, "sport_name": "NRL",
            "participants": ["Warriors", "Storm"],
            "kickoff_utc": (now + timedelta(hours=6)).isoformat(),
            "proposed_selection": "Warriors", "market_type": "h2h",
            "research_reason": "Form favours the home side.",
            "uncertainty_flags": [],
            "market_anchor": {
                "source": "Example Books", "favourite": "Warriors", "selection": "Warriors",
                "market": "h2h", "line": None, "price": 1.9,
                "observed_at_utc": (now - timedelta(minutes=5)).isoformat(),
                "url": "https://example.com/odds",
            },
        }
        record = {"selected_sport_keys": [], "candidates": [candidate], "warnings": []}
        with patch("research_shortlist.run_research_shortlist", return_value=record):
            gwm.run()
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(len(saved["research_leads"]), 1)
        self.assertEqual(saved["research_leads"][0]["match"], "Warriors vs Storm")


if __name__ == "__main__":
    unittest.main()
