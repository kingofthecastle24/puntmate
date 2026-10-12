"""
_recently_actioned_slugs()'s 4-day dedupe window must be computed against
Auckland "today", not server-local/UTC "today" (2026-10-11, external audit
item 6) -- state filenames are dated by run_date, which is nz_today(), so
the cutoff needs to use the same calendar to stay aligned.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch
from datetime import timezone, timedelta, datetime as real_datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main


class RecentlyActionedSlugsNzDateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_root = pm_main.REPO_ROOT
        pm_main.REPO_ROOT = self.tmp
        self.state_dir = os.path.join(self.tmp, "data", "state")
        os.makedirs(self.state_dir, exist_ok=True)

    def tearDown(self):
        pm_main.REPO_ROOT = self._orig_root
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_state_file(self, datestr, slug):
        with open(os.path.join(self.state_dir, f"{datestr}_{slug}.json"), "w") as f:
            json.dump({"state": "PUBLISHED"}, f)

    def test_a_fixture_right_at_the_utc_vs_nz_date_seam_is_not_dropped_early(self):
        # UTC instant where the UTC calendar date is one day BEHIND the NZ
        # business date (e.g. 2026-10-11 20:00 UTC -> 2026-10-12 NZDT). A
        # state file dated with today's NZ business date must still count
        # as "today" (0 days old), not be miscounted against a UTC cutoff
        # that thinks today is still the 11th.
        self._seed_state_file("2026-10-12", "some_fixture")
        fixed_now = real_datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
        with patch("main.nz_today", return_value="2026-10-12"):
            with patch("main.datetime") as mock_dt:
                mock_dt.now.return_value = fixed_now
                slugs = pm_main._recently_actioned_slugs(days=4)
        self.assertIn("some_fixture", slugs)

    def test_a_fixture_older_than_the_window_is_excluded(self):
        self._seed_state_file("2026-09-01", "stale_fixture")
        with patch("main.nz_today", return_value="2026-10-12"):
            slugs = pm_main._recently_actioned_slugs(days=4)
        self.assertNotIn("stale_fixture", slugs)


if __name__ == "__main__":
    unittest.main()
