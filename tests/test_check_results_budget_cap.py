"""
Tests for check_results.py's 2026-10-15 budgeting (Section 6): the
/scores endpoint costs 2 credits per sport query, not the "free tier, no
extra quota cost" the old comment claimed — rotating through all 14
registered sports with unrestricted polling could cost 14 x 2 x 31 = 868
credits/month before a single odds call. These pin down the daily cap,
the urgency-based rotation, the settlement_pending_external flag, and
that a genuinely exhausted budget blocks every scores call.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import check_results
import quota_budget

TODAY = datetime.now(timezone.utc).date()


def _pick(id_, sport_key, days_ago, home="Home", away="Away", pick_name="Home"):
    return {
        "id": id_, "sport_key": sport_key, "result": "pending", "pnl": None,
        "date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "match": f"{home} vs {away}", "home_team": home, "away_team": away,
        "pick": pick_name, "odds": 1.8, "market": "Head to Head",
    }


class CheckResultsBudgetCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_picks_path = check_results.PICKS_PATH
        check_results.PICKS_PATH = os.path.join(self.tmp, "picks.json")
        self._orig_budget_path = quota_budget.BUDGET_PATH
        quota_budget.BUDGET_PATH = os.path.join(self.tmp, "quota_budget.json")

    def tearDown(self):
        check_results.PICKS_PATH = self._orig_picks_path
        quota_budget.BUDGET_PATH = self._orig_budget_path
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_picks(self, picks):
        with open(check_results.PICKS_PATH, "w") as f:
            json.dump(picks, f)

    def _fund_period(self, remaining=500):
        quota_budget.start_new_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC,
                                       confirmed_provider_remaining=remaining)

    # ---- the daily cap itself ----

    @patch("check_results.fetch_scores", return_value=[])
    def test_only_two_distinct_sports_are_checked_per_run(self, mock_fetch):
        self._fund_period()
        picks = [
            _pick("a", "sport_a", days_ago=0), _pick("b", "sport_b", days_ago=0),
            _pick("c", "sport_c", days_ago=0),
        ]
        self._write_picks(picks)
        check_results.check_and_resolve()
        self.assertEqual(mock_fetch.call_count, 2)

    @patch("check_results.fetch_scores", return_value=[])
    def test_most_urgent_sports_are_checked_first(self, mock_fetch):
        self._fund_period()
        # sport_old is about to fall out of the 3-day window; sport_new just started.
        picks = [
            _pick("a", "sport_new", days_ago=0),
            _pick("b", "sport_old", days_ago=check_results.STALE_PENDING_DAYS - 1),
            _pick("c", "sport_mid", days_ago=1),
        ]
        self._write_picks(picks)
        check_results.check_and_resolve()
        checked = [c.args[0] for c in mock_fetch.call_args_list]
        self.assertEqual(checked[0], "sport_old")

    @patch("check_results.fetch_scores", return_value=[])
    def test_skipped_sport_charges_zero_budget(self, mock_fetch):
        self._fund_period()
        picks = [
            _pick("a", "sport_a", days_ago=0), _pick("b", "sport_b", days_ago=0),
            _pick("c", "sport_c", days_ago=0),
        ]
        self._write_picks(picks)
        check_results.check_and_resolve()
        rec = quota_budget.get_period(quota_budget.CURRENT_PERIOD_KEY)
        self.assertEqual(rec["buckets"][quota_budget.SCORES]["charged"],
                          2 * check_results.SCORES_CREDIT_COST)

    # ---- settlement_pending_external flag ----

    @patch("check_results.fetch_scores", return_value=[])
    def test_urgent_pick_in_a_skipped_sport_is_flagged(self, _mock_fetch):
        self._fund_period()
        picks = [
            _pick("a", "sport_a", days_ago=check_results.STALE_PENDING_DAYS - 1),
            _pick("b", "sport_b", days_ago=check_results.STALE_PENDING_DAYS - 1),
            _pick("c", "sport_c", days_ago=check_results.STALE_PENDING_DAYS - 1),
        ]
        self._write_picks(picks)
        check_results.check_and_resolve()
        with open(check_results.PICKS_PATH) as f:
            saved = {p["id"]: p for p in json.load(f)}
        flagged = [pid for pid, p in saved.items() if p.get("settlement_pending_external")]
        self.assertEqual(len(flagged), 1)  # exactly the one sport that missed the cap

    @patch("check_results.fetch_scores", return_value=[])
    def test_non_urgent_pick_in_a_skipped_sport_is_not_flagged(self, _mock_fetch):
        self._fund_period()
        picks = [
            _pick("a", "sport_a", days_ago=0), _pick("b", "sport_b", days_ago=0),
            _pick("c", "sport_c", days_ago=0),  # not urgent, just skipped
        ]
        self._write_picks(picks)
        check_results.check_and_resolve()
        with open(check_results.PICKS_PATH) as f:
            saved = {p["id"]: p for p in json.load(f)}
        self.assertNotIn("settlement_pending_external", saved["c"])

    # ---- budget exhaustion blocks every scores call ----

    @patch("check_results.fetch_scores", return_value=[])
    def test_exhausted_budget_blocks_every_scores_call(self, mock_fetch):
        quota_budget.init_exhausted_period(quota_budget.CURRENT_PERIOD_KEY, quota_budget.CURRENT_PERIOD_RESET_UTC)
        picks = [_pick("a", "sport_a", days_ago=0)]
        self._write_picks(picks)
        check_results.check_and_resolve()
        mock_fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
