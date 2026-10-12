"""
data/latest_run.json should carry a per-sport fixture count for the run's
window (2026-10-11, external audit item 6: "surface UFC/Test-rugby
fixture/odds availability") -- so "0 fixtures today" for a priority sport
is visible without reading the raw CI log where fetch_odds prints it.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import fetch_odds


class FixtureAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR)
        pm_main.LATEST_RUN_PATH = os.path.join(self.tmp, "data", "latest_run.json")
        pm_main.CARDS_DIR = os.path.join(self.tmp, "data", "cards")

    def tearDown(self):
        pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR = self._orig
        fetch_odds.LAST_FETCH_ERRORS = []
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("fetch_odds.fetch_upcoming_odds", return_value=[])
    def test_empty_day_records_zero_counts_for_every_configured_sport(self, _mock):
        fetch_odds.LAST_FETCH_ERRORS = []
        pm_main.run()
        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertIn("fixture_availability", saved)
        self.assertEqual(saved["fixture_availability"]["mma_mixed_martial_arts"], 0)
        self.assertEqual(saved["fixture_availability"]["rugbyunion_international"], 0)
        self.assertEqual(set(saved["fixture_availability"]), set(fetch_odds.SPORTS))

    @patch("fetch_odds.fetch_upcoming_odds")
    def test_counts_reflect_what_was_actually_fetched(self, mock_fetch):
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


if __name__ == "__main__":
    unittest.main()
