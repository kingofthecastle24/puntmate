"""
Tests for main.py's Degen Watch wiring (2026-10-11, Micah): on a genuine
no-bet day, generate_pick.select_closest_to_passing's result (if any)
gets rendered and attached to run_data["degen_watch"], independent of the
watchlist and never affecting the main NO_BET write if rendering fails.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import fetch_odds
import quota_budget

RESEARCH_RECORD_NRL_SELECTED = {"selected_sport_keys": ["rugbyleague_nrl"], "candidates": [], "warnings": []}

SAMPLE_MATCH = {
    "sport": "rugbyleague_nrl",
    "sport_label": "NRL",
    "match": "Warriors vs Storm",
    "home_team": "Warriors",
    "away_team": "Storm",
    "kickoff": "2026-10-11T08:00:00Z",
}

DEGEN_CANDIDATE = {
    "cause": "not_backable",
    "match": "Warriors vs Storm",
    "sport_label": "NRL",
    "market_type": "h2h",
    "selection": "Storm to Win",
    "odds": 2.10,
    "reason": "edge too thin to back",
    "evidence_sufficient": True,
    "our_probability": 54.0,
    "implied_probability": 50.0,
    "edge_pct": 4.2,
    "min_value_edge_pct": 7.0,
}

NO_BET_PICK_WITH_REJECTED = {
    "has_pick": False,
    "status": "NO_VALUE",
    "reasoning": "Nothing cleared the bar today.",
    "research_warnings": [],
    "rejected_candidates": [DEGEN_CANDIDATE],
}

NO_BET_PICK_NO_REJECTED = {
    "has_pick": False,
    "status": "NO_VALUE",
    "reasoning": "Nothing cleared the bar today.",
    "research_warnings": [],
    "rejected_candidates": [],
}


class MainDegenWatchWiringTests(unittest.TestCase):
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

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_degen_watch_attached_to_run_data_when_a_candidate_qualifies(self, _odds, _news, _research):
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(NO_BET_PICK_WITH_REJECTED)), \
             patch("main.render_degen_watch_card", return_value={"ok": True, "file": "/fake/path/card.png"}) as mock_render:
            pm_main.run()
            mock_render.assert_called_once()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertIn("degen_watch", saved)
        self.assertEqual(saved["degen_watch"]["candidate"]["match"], "Warriors vs Storm")
        self.assertEqual(saved["degen_watch"]["card_file"], "/fake/path/card.png")
        self.assertIn("watchlist", saved)  # independent of the watchlist

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_no_degen_watch_key_when_nothing_qualifies(self, _odds, _news, _research):
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(NO_BET_PICK_NO_REJECTED)), \
             patch("main.render_degen_watch_card") as mock_render:
            pm_main.run()
            mock_render.assert_not_called()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertNotIn("degen_watch", saved)

    @patch("research_shortlist.run_research_shortlist", return_value=dict(RESEARCH_RECORD_NRL_SELECTED))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_card_render_failure_still_records_the_candidate_with_no_card_file(self, _odds, _news, _research):
        # render_degen_watch_card returns None on failure (never raises) --
        # the day's NO_BET write must still go through with the candidate
        # recorded, just without a card to post to Instagram.
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(NO_BET_PICK_WITH_REJECTED)), \
             patch("main.render_degen_watch_card", return_value=None):
            pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertIn("degen_watch", saved)
        self.assertIsNone(saved["degen_watch"]["card_file"])
        self.assertEqual(saved["degen_watch"]["candidate"]["match"], "Warriors vs Storm")


if __name__ == "__main__":
    unittest.main()
