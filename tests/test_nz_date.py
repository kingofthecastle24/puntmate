"""
Tests for nz_date.py (2026-10-11, external audit item 6): "use Pacific/
Auckland business dates ... not a single fixed UTC cron shift." These
pin down nz_today() across both NZ daylight-saving regimes (NZST, UTC+12,
roughly Apr-Sep; NZDT, UTC+13, roughly Sep-Apr) and across the transition
itself, since that's exactly the drift main.py's run_date used to ignore
by just taking the raw UTC calendar date.
"""
import os, sys, unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from nz_date import nz_today, nz_now_iso


class NzTodayDstTests(unittest.TestCase):
    def test_nzdt_generate_run_lands_on_the_next_utc_day(self):
        # generate.yml's cron fires 20:00 UTC. In NZDT (UTC+13) that is
        # 09:00 the FOLLOWING day in Auckland -- a naive UTC date here
        # would be one calendar day behind the real NZ business date.
        now_utc = datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(nz_today(now_utc), "2026-10-12")

    def test_nzst_generate_run_lands_on_the_next_utc_day_too(self):
        # In NZST (UTC+12), the same 20:00 UTC cron fire is 08:00 the
        # following day in Auckland -- still the next UTC calendar day,
        # just one hour earlier locally than the NZDT case above.
        now_utc = datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc)
        self.assertEqual(nz_today(now_utc), "2026-07-12")

    def test_nzdt_and_nzst_give_different_local_hours_for_the_same_utc_cron_time(self):
        # This is the actual bug: one fixed UTC cron time is 8am NZT only
        # half the year. Confirm nz_now_iso's local hour actually shifts
        # across the transition for the identical UTC instant-of-day.
        nzdt_hour = int(nz_now_iso(datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc))[11:13])
        nzst_hour = int(nz_now_iso(datetime(2026, 7, 11, 20, 0, tzinfo=timezone.utc))[11:13])
        self.assertEqual(nzdt_hour, 9)
        self.assertEqual(nzst_hour, 8)
        self.assertNotEqual(nzdt_hour, nzst_hour)

    def test_spring_forward_transition_2026_09_27_does_not_crash_or_skip_a_date(self):
        # NZ springs forward on the last Sunday of September (2026-09-27,
        # 2am -> 3am NZST->NZDT). Business-date continuity across it matters
        # more than the exact clock time -- zoneinfo handles the wall-clock
        # gap internally, this just confirms the date progresses sanely.
        before = nz_today(datetime(2026, 9, 26, 11, 0, tzinfo=timezone.utc))   # ~11pm NZST on the 26th
        after = nz_today(datetime(2026, 9, 27, 11, 0, tzinfo=timezone.utc))    # ~midnight NZDT on the 28th
        self.assertEqual(before, "2026-09-26")
        self.assertEqual(after, "2026-09-28")

    def test_fall_back_transition_2026_04_05_does_not_crash_or_duplicate_a_date(self):
        # NZ falls back on the first Sunday of April (2026-04-05, 3am ->
        # 2am NZDT->NZST).
        before = nz_today(datetime(2026, 4, 4, 11, 0, tzinfo=timezone.utc))   # NZDT, afternoon on the 5th
        after = nz_today(datetime(2026, 4, 5, 13, 0, tzinfo=timezone.utc))    # NZST, early morning on the 6th
        self.assertEqual(before, "2026-04-05")
        self.assertEqual(after, "2026-04-06")

    def test_defaults_to_the_real_current_time_when_called_with_no_argument(self):
        # Just confirm it runs and returns a plausible-looking date string
        # without an explicit now_utc -- doesn't assert an exact value
        # since this test's "now" is whenever CI happens to run it.
        result = nz_today()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
