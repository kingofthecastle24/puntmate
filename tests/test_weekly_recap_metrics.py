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
from copy_validator import check_internal_leak


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

    def test_roi_is_computed_and_does_reach_the_public_telegram_text(self):
        # Micah, 2026-10-11: ROI can be shared on Telegram -- this script's
        # ONLY output surface (it never posts to Facebook or Instagram) --
        # just never on Facebook or Instagram themselves.
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win", "odds": 2.0},   # +1.0
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss", "odds": 1.5},  # -1.0
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 3.0},     # +2.0
        ])
        start, end = wr.week_window()
        picks = wr.load_picks()
        stats, overall = wr.build_stats(picks, start, end)

        # Overall: net +2.0 over 3 settled picks -> +66.7% flat-stake ROI.
        self.assertEqual(wr.overall_roi_pct(picks, start, end), 66.7)
        self.assertEqual(wr.overall_roi_pct(picks, start, end, bet_types={"INVESTOR_BET"}), 0.0)
        self.assertEqual(wr.overall_roi_pct(picks, start, end, bet_types={"PUNTER_BET"}), 200.0)

        public_text = wr.build_recap_text(stats, overall, 0, start, end, picks=picks)
        self.assertIn("ROI this week", public_text)
        self.assertIn("+66.7%", public_text)
        self.assertIn("ROI +0.0%", public_text)    # Investor line
        self.assertIn("ROI +200.0%", public_text)  # Punter line

    def test_roi_excludes_picks_outside_the_week_window(self):
        d = self._today()
        old_date = "2020-01-01"
        self._write_picks([
            {"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 2.0},
            {"date": old_date, "bet_type": "PUNTER_BET", "result": "loss", "odds": 5.0},
        ])
        start, end = wr.week_window()
        picks = wr.load_picks()
        # Only today's win counts -> +100%, not dragged down by the 2020 loss.
        self.assertEqual(wr.overall_roi_pct(picks, start, end), 100.0)

    def test_roi_is_omitted_when_picks_not_supplied(self):
        # build_recap_text's picks= param is optional so callers that don't
        # need ROI (and tests of other behaviour) keep working unchanged.
        d = self._today()
        self._write_picks([{"date": d, "bet_type": "PUNTER_BET", "result": "win", "odds": 2.0}])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end)  # no picks= arg
        self.assertNotIn("ROI", text)

    def test_added_metrics_still_pass_the_internal_leak_gate(self):
        d = self._today()
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win", "odds": 1.80},
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss", "odds": 2.20},
            {"date": d, "bet_type": "PUNTER_BET", "result": "push", "odds": 2.5},
        ])
        start, end = wr.week_window()
        picks = wr.load_picks()
        stats, overall = wr.build_stats(picks, start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end, picks=picks)
        self.assertEqual(check_internal_leak(text), [])


    def test_weekly_recap_never_imports_an_instagram_or_facebook_poster(self):
        # Regression guard for Micah's rule (2026-10-11): ROI can go out on
        # Telegram, never Facebook or Instagram. This file posting the
        # recap through ANYTHING other than post_telegram would put ROI
        # content somewhere it was never approved for.
        src = open(wr.__file__).read()
        self.assertNotIn("post_instagram", src)
        self.assertNotIn("post_facebook", src)
        self.assertIn("post_telegram", src)


if __name__ == "__main__":
    unittest.main()
