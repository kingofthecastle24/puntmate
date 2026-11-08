"""Tests for the Sunday recap presentation fixes (2026-11-08).

Two regressions covered:
1. Public week dates must render short ('2-8 Nov 2026'), never the ISO
   span, and the as-of stamp must sit on its own rendered line instead of
   being joined into the subline with a middle dot.
2. The settled UFC Vegas 124 weekend multi (leg 6 verified LOSS via the
   official UFC results pages, 2026-11-08) must read as a settled LOSS in
   the canonical ledger, never as a not-yet-played pick.
"""

import json
import os
import sys
import types
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from public_delivery import format_publication_week, render_recap, eligible


class FormatPublicationWeekTests(unittest.TestCase):
    def test_same_month_collapses_to_day_range(self):
        self.assertEqual(format_publication_week("2026-11-02", "2026-11-08"), "2-8 Nov 2026")

    def test_cross_month_spells_both_months(self):
        self.assertEqual(format_publication_week("2026-10-26", "2026-11-01"), "26 Oct - 1 Nov 2026")

    def test_cross_year_spells_both_years(self):
        self.assertEqual(format_publication_week("2026-12-28", "2027-01-03"), "28 Dec 2026 - 3 Jan 2027")

    def test_no_iso_dates_in_output(self):
        out = format_publication_week("2026-11-02", "2026-11-08")
        self.assertNotIn("2026-11", out)


class RenderRecapLayoutTests(unittest.TestCase):
    def _capture(self, lines):
        captured = {}
        fake = types.ModuleType("render_public_record")
        fake.render_record = lambda payload, output: captured.update(payload)
        sys.modules["render_public_record"] = fake
        try:
            render_recap(lines, "unused.png")
        finally:
            del sys.modules["render_public_record"]
        return captured

    def test_asof_stamp_is_its_own_row_not_joined_to_subline(self):
        lines = ["Publication week 2-8 Nov 2026", "Preview as of 08 Nov 2026 19:11 NZDT",
                 "INVESTOR: 1W - 1L | 50%", "Multis: 0W - 1L | strike rate 0%"]
        payload = self._capture(lines)
        self.assertEqual(payload["subline"], "Publication week 2-8 Nov 2026")
        self.assertEqual(payload["rows"][0], "Preview as of 08 Nov 2026 19:11 NZDT")
        self.assertNotIn("\u00b7", payload["subline"])

    def test_all_content_lines_survive(self):
        lines = ["Publication week 2-8 Nov 2026", "Preview as of 08 Nov 2026 19:11 NZDT",
                 "INVESTOR: 1W - 1L | 50%"]
        payload = self._capture(lines)
        self.assertEqual([payload["subline"]] + payload["rows"], lines)


class UfcMultiSettlementTests(unittest.TestCase):
    def test_verified_leg6_loss_is_settled_once_in_canonical_ledger(self):
        with open(os.path.join(ROOT, "data", "results", "picks_ledger.json")) as f:
            ledger = json.load(f)
        entry = [p for p in ledger["picks"] if p["id"] == "2026-11-06_research_UFC_Vegas_124_Weekend_Multi_v4"]
        self.assertEqual(len(entry), 1)
        pick = entry[0]
        self.assertEqual(pick["result"], "LOSS")
        self.assertTrue(eligible(pick), "settled multi must carry outcome_source and outcome_checked_at")
        self.assertIn("ufc.com", pick["outcome_source"])
        self.assertNotIn("pending_label", pick)


if __name__ == "__main__":
    unittest.main()
