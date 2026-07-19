"""
Tests for generate_weekend_multi.py — the weekend-pool Punter/Gambler-
Degenerate multi pipeline (2026-07-19, Micah).
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_weekend_multi as gwm

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


class GenerateWeekendMultiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (gwm.REPO_ROOT, gwm.LATEST_WEEKEND_RUN_PATH, gwm.CARDS_DIR)
        gwm.REPO_ROOT = self.tmp
        gwm.LATEST_WEEKEND_RUN_PATH = os.path.join(self.tmp, "data", "latest_weekend_run.json")
        gwm.CARDS_DIR = os.path.join(self.tmp, "data", "cards")

    def tearDown(self):
        gwm.REPO_ROOT, gwm.LATEST_WEEKEND_RUN_PATH, gwm.CARDS_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_wide_window_is_requested_and_multis_saved(self, mock_fetch, *_mocks):
        mock_fetch.return_value = WEEKEND_MATCHES
        gwm.run()

        mock_fetch.assert_called_once_with(hours_ahead=gwm.WEEKEND_HOURS_AHEAD)
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(len(saved["punter_multi_legs"]), 3)
        self.assertEqual(saved["gambler_multi_legs"], [])
        self.assertEqual(saved["hours_ahead"], gwm.WEEKEND_HOURS_AHEAD)

    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_build_multis_true_is_passed_through(self, mock_fetch, *_mocks):
        mock_fetch.return_value = WEEKEND_MATCHES
        with patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT)) as mock_gen:
            gwm.run()
        mock_gen.assert_called_once()
        self.assertTrue(mock_gen.call_args.kwargs.get("build_multis"))

    @patch("main.render_multi_cards")
    @patch("generate_pick.generate_pick_for_matches", return_value=dict(WEEKEND_PICK_RESULT))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds")
    def test_only_qualifying_tier_gets_rendered(self, mock_fetch, _fetch_news, _gen, mock_render):
        mock_fetch.return_value = WEEKEND_MATCHES
        gwm.run()
        # Punter cleared 3 legs -> rendered; Gambler is empty -> never rendered.
        rendered_tiers = [call.args[1] for call in mock_render.call_args_list]
        self.assertIn("punter", rendered_tiers)
        self.assertNotIn("gambler", rendered_tiers)

    @patch("fetch_odds.fetch_upcoming_odds", return_value=[])
    def test_no_fixtures_in_window_stays_silent(self, mock_fetch):
        gwm.run()
        with open(gwm.LATEST_WEEKEND_RUN_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["punter_multi_legs"], [])
        self.assertEqual(saved["gambler_multi_legs"], [])
        self.assertEqual(saved["fixture_count"], 0)


if __name__ == "__main__":
    unittest.main()
