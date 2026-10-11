"""
Tests for the run-status + stale-latest_run.json fix (2026-10-11, external
audit item 2): every call to main.run() must write a fresh run_id/run_date/
status to data/latest_run.json, on every exit path — including empty
fixtures and Odds API failures, which previously returned without writing
anything at all and left a stale prior-day file in place.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import fetch_odds
import run_status


class EmptyFixturesWriteTests(unittest.TestCase):
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
    def test_genuinely_zero_fixtures_still_writes_a_fresh_run_with_no_value_status(self, _mock):
        fetch_odds.LAST_FETCH_ERRORS = []  # no errors -> genuinely nothing today
        pm_main.run()

        self.assertTrue(os.path.exists(pm_main.LATEST_RUN_PATH))
        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertEqual(saved["status"], run_status.NO_VALUE)
        self.assertFalse(saved["pick"]["has_pick"])
        self.assertIn("run_id", saved)
        self.assertIn("run_date", saved)
        self.assertEqual(saved["odds_api_errors"], [])

    @patch("fetch_odds.fetch_upcoming_odds", return_value=[])
    def test_odds_api_failure_on_every_sport_is_an_operational_failure_not_no_value(self, _mock):
        # Simulate every sport's fetch raising (dead key / rate limit) --
        # fetch_upcoming_odds itself still returns [] (it swallows per-sport
        # errors) but populates LAST_FETCH_ERRORS, which main.py must check.
        fetch_odds.LAST_FETCH_ERRORS = [
            {"sport": "rugbyleague_nrl", "status_code": 401, "error": "Unauthorized"},
            {"sport": "soccer_epl", "status_code": 401, "error": "Unauthorized"},
        ]
        pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertEqual(saved["status"], run_status.ODDS_API_ERROR)
        self.assertIn(saved["status"], run_status.OPERATIONAL_FAILURE_STATUSES)
        self.assertFalse(saved["pick"]["has_pick"])
        self.assertEqual(len(saved["odds_api_errors"]), 2)

    @patch("fetch_odds.fetch_upcoming_odds", return_value=[])
    def test_api_outage_after_a_prior_successful_run_cannot_reuse_yesterdays_pick(self, _mock):
        # Seed yesterday's successful run on disk, exactly as a real prior
        # day's latest_run.json would look.
        os.makedirs(os.path.dirname(pm_main.LATEST_RUN_PATH), exist_ok=True)
        yesterday = {
            "run_id": "local-yesterday123",
            "run_date": "2026-10-10",
            "run_ts": "2026-10-10T08:00:00+00:00",
            "status": run_status.PICK_READY,
            "pick": {
                "has_pick": True,
                "status": run_status.PICK_READY,
                "match": "Yesterday Team A vs Yesterday Team B",
                "selection": "Team A to Win",
                "odds": "1.80",
            },
        }
        with open(pm_main.LATEST_RUN_PATH, "w") as f:
            json.dump(yesterday, f)

        # Today the Odds API is dead for every sport.
        fetch_odds.LAST_FETCH_ERRORS = [
            {"sport": "rugbyleague_nrl", "status_code": 429, "error": "Too Many Requests"},
        ]
        pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        # The file was overwritten with a fresh, honestly-failed run --
        # not left stale, and not silently carrying yesterday's pick forward.
        self.assertNotEqual(saved["run_id"], "local-yesterday123")
        self.assertNotEqual(saved["run_date"], "2026-10-10")
        self.assertEqual(saved["status"], run_status.ODDS_API_ERROR)
        self.assertFalse(saved["pick"]["has_pick"])
        self.assertNotEqual(saved["pick"].get("match"), "Yesterday Team A vs Yesterday Team B")


class RunIdUniquenessTests(unittest.TestCase):
    def test_new_run_id_uses_github_run_id_when_present(self):
        with patch.dict(os.environ, {"GITHUB_RUN_ID": "9988776655"}):
            self.assertEqual(pm_main._new_run_id(), "9988776655")

    def test_new_run_id_falls_back_to_a_fresh_local_id_without_github_run_id(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GITHUB_RUN_ID", None)
            first = pm_main._new_run_id()
            second = pm_main._new_run_id()
        self.assertTrue(first.startswith("local-"))
        self.assertNotEqual(first, second)  # never reused across invocations


if __name__ == "__main__":
    unittest.main()
