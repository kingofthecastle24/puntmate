"""
Tests for weekly_recap.py's added metrics (2026-10-11, external audit item
5: "add only missing metrics: ... average decimal odds ... sample size ...
Define voids/pushes separately"). Reuses the existing Telegram outcome
tracker (data/picks.json + weekly_recap.py) rather than building a second
ledger -- these tests exercise build_stats()/build_recap_text() directly,
same as the existing Phase 6 tests in test_phases_4_5_6.py.
"""
import os, sys, json, shutil, tempfile, unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import weekly_recap as wr
from copy_validator import check_internal_leak, check_staking_language


class WeeklyRecapMetricsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (wr.PICKS_PATH, wr.STATE_DIR, wr.RECAP_PATH, wr.RECORD_START_PATH)
        wr.PICKS_PATH = os.path.join(self.tmp, "picks.json")
        wr.STATE_DIR = os.path.join(self.tmp, "state")
        wr.RECAP_PATH = os.path.join(self.tmp, "RECAP.md")
        wr.RECORD_START_PATH = os.path.join(self.tmp, "record_start_date")
        os.makedirs(wr.STATE_DIR, exist_ok=True)

    def tearDown(self):
        wr.PICKS_PATH, wr.STATE_DIR, wr.RECAP_PATH, wr.RECORD_START_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_picks(self, picks):
        with open(wr.PICKS_PATH, "w") as f:
            json.dump(picks, f)

    def _today(self):
        return datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

    def test_push_is_a_distinct_bucket_not_miscounted_as_pending(self):
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 2.0},
            {"date": d, "bet_type": "PUNTER_BET", "result": "push", "odds": 1.90},
        ])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        self.assertEqual(overall["pushes"], 1)
        self.assertEqual(overall["pending"], 0)  # the push must NOT land here
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertIn("1 push", text)
        self.assertNotIn("still to settle", text)  # a push isn't "still pending"

    def test_average_decimal_odds_is_reported_for_settled_picks_only(self):
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win", "odds": 1.80},
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss", "odds": 2.20},
            {"date": d, "bet_type": "INVESTOR_BET", "result": "pending", "odds": 3.50},
        ])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        # Average of the two SETTLED picks only (1.80, 2.20) -> 2.00, the
        # pending pick's 3.50 must not drag the average toward it.
        self.assertEqual(wr.average_odds(overall), 2.00)
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertIn("Avg odds 2.00", text)

    def test_small_sample_is_flagged(self):
        d = self._today()
        # Only 2 settled picks -- well under SMALL_SAMPLE_FLOOR.
        self._write_picks([
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 2.0},
            {"date": d, "bet_type": "PUNTER_BET", "result": "loss", "odds": 1.9},
        ])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertIn("Small sample", text)

    def test_a_week_of_only_pushes_is_not_reported_as_quiet(self):
        d = self._today()
        self._write_picks([{"date": d, "bet_type": "PUNTER_BET", "result": "push", "odds": 2.0}])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertNotIn("no picks put up", text)
        self.assertIn("1 push", text)

    def test_internal_roi_report_is_computed_but_never_in_public_text(self):
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win", "odds": 2.0},   # +1.0
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss", "odds": 1.5},  # -1.0
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 3.0},     # +2.0
        ])
        start, end = wr.week_window()
        picks = wr.load_picks()
        stats, overall = wr.build_stats(picks, start, end)
        report = wr._internal_metrics_report(stats, overall, picks, start, end)
        # Overall: net +2.0 over 3 settled picks -> +66.7% flat-stake ROI.
        self.assertIn("Overall ROI: +66.7%", report)
        self.assertIn("Investor ROI: +0.0%", report)   # +1.0 - 1.0 over 2 picks
        self.assertIn("Punter ROI: +200.0%", report)    # +2.0 over 1 pick

        public_text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertNotIn("ROI", public_text)

    def test_internal_roi_report_excludes_picks_outside_the_week_window(self):
        d = self._today()
        old_date = "2020-01-01"
        self._write_picks([
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 2.0},
            {"date": old_date, "bet_type": "PUNTER_BET", "result": "loss", "odds": 5.0},
        ])
        start, end = wr.week_window()
        picks = wr.load_picks()
        stats, overall = wr.build_stats(picks, start, end)
        report = wr._internal_metrics_report(stats, overall, picks, start, end)
        self.assertIn("n=1", report)  # only today's pick, not the 2020 one

    def test_added_metrics_still_pass_the_public_copy_gates(self):
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win", "odds": 1.80},
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss", "odds": 2.20},
            {"date": d, "bet_type": "PUNTER_BET", "result": "push", "odds": 2.5},
        ])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertEqual(check_internal_leak(text), [])
        self.assertEqual(check_staking_language(text), [])


if __name__ == "__main__":
    unittest.main()
