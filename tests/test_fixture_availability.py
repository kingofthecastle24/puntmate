"""
data/latest_run.json carries a per-sport fixture count (2026-10-11,
external audit item 6: "surface UFC/Test-rugby fixture/odds
availability"). 2026-10-15 redesign: under the two-stage pipeline, most
sports are never queried at all most days (Stage 1 shortlists at most
two), so this dict's scope narrowed from "every configured sport" to
"only the sport(s) Stage 2 actually queried this run" -- counting an
un-queried sport as 0 would misleadingly look identical to "queried,
found nothing".
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import fetch_odds
import quota_budget

RESEARCH_RECORD_TWO_SELECTED = {
    "selected_sport_keys": ["rugbyunion_international", "mma_mixed_martial_arts"],
    "candidates": [], "warnings": [],
}


class FixtureAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR)
        pm_main.LATEST_RUN_PATH = os.path.join(self.tmp, "data", "latest_run.json")
        pm_main.CARDS_DIR = os.path.join(self.tmp, "data", "cards")
        self._orig_budget_path = quota_budget.BUDGET_PATH
        quota_budget.BUDGET_PATH = os.path.join(self.tmp, "quota_budget.json")
        quota_budget.start_new_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC,
                                       confirmed_provider_remaining=500)

    def tearDown(self):
        pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR = self._orig
        quota_budget.BUDGET_PATH = self._orig_budget_path
        fetch_odds.LAST_FETCH_ERRORS = []
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_TWO_SELECTED))
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[])
    def test_empty_day_records_zero_counts_for_only_the_queried_sports(self, _mock, _research):
        fetch_odds.LAST_FETCH_ERRORS = []
        pm_main.run()
        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertIn("fixture_availability", saved)
        self.assertEqual(saved["fixture_availability"]["mma_mixed_martial_arts"], 0)
        self.assertEqual(saved["fixture_availability"]["rugbyunion_international"], 0)
        # Scope is now exactly what was queried -- not the full registry.
        self.assertEqual(set(saved["fixture_availability"]), {"rugbyunion_international", "mma_mixed_martial_arts"})

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_TWO_SELECTED))
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_counts_reflect_what_was_actually_fetched(self, mock_fetch, _research):
        mock_fetch.return_value = [
            {"sport": "rugbyunion_international", "match": "NZ vs Ireland",
             "home_team": "NZ", "away_team": "Ireland", "kickoff": "2026-10-12T08:00:00Z",
             "odds": {"home": 1.50, "away": 2.80, "draw": None},
             "implied_probs": {"home": 0.60, "away": 0.33, "draw": 0}},
            {"sport": "rugbyunion_international", "match": "Australia vs Argentina",
             "home_team": "Australia", "away_team": "Argentina", "kickoff": "2026-10-12T10:00:00Z",
             "odds": {"home": 1.60, "away": 2.50, "draw": None},
             "implied_probs": {"home": 0.56, "away": 0.37, "draw": 0}},
        ]
        fetch_odds.LAST_FETCH_ERRORS = []
        with patch("fetch_news.fetch_news", return_value={"warnings": []}), \
             patch("generate_pick.generate_pick_for_matches", return_value={
                 "has_pick": False, "status": "NO_VALUE", "reasoning": "n/a", "research_warnings": [],
             }):
            pm_main.run()
        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["fixture_availability"]["rugbyunion_international"], 2)
        self.assertEqual(saved["fixture_availability"]["mma_mixed_martial_arts"], 0)

    @patch("research_shortlist.run_research_shortlist", return_value={"selected_sport_keys": [], "candidates": [], "warnings": []})
    def test_no_sport_selected_means_an_empty_fixture_availability_dict(self, _research):
        # Stage 1 found nothing worth pricing -- Stage 2 never runs, so
        # there is nothing to report counts for at all (not zeroes for
        # every sport, an empty dict -- nothing was queried).
        pm_main.run()
        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["fixture_availability"], {})
        self.assertEqual(saved["fallback_reason"], "no_sport_selected")


if __name__ == "__main__":
    unittest.main()
