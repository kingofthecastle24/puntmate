"""Regression: card renders must be dated by the NZ run_date, not UTC now.

build_review_package.py / build_weekend_multi_package.py freeze cards by
globbing data/cards/ for the NZ run_date prefix. render_pick/render_multi/
render_degen_watch default date_str to datetime.now(timezone.utc), so a run
executing after 13:00 UTC (NZ next day) used to render under the wrong date
prefix and the freeze step refused the package (Actions runs 41351709593,
41731936219, 41929370584). These tests pin the caller wiring: every render
entry point in main.py must thread an explicit date_str through.
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main  # noqa: E402
import render_brand_templates  # noqa: E402


class RenderDateThreadingTest(unittest.TestCase):
    def test_render_card_passes_date_str(self):
        with mock.patch.object(render_brand_templates, "render_pick",
                               return_value={"ok": True, "files": {}}) as m:
            main.render_card({"match": "A vs B"}, date_str="2026-11-06")
        self.assertEqual(m.call_args.kwargs["date_str"], "2026-11-06")

    def test_render_multi_cards_passes_date_str(self):
        with mock.patch.object(render_brand_templates, "render_multi",
                               return_value={"ok": True, "files": {}}) as m:
            main.render_multi_cards({"match": "Weekend Multi"}, "punter", [], date_str="2026-11-06")
        self.assertEqual(m.call_args.kwargs["date_str"], "2026-11-06")

    def test_render_degen_watch_card_passes_date_str(self):
        with mock.patch.object(render_brand_templates, "render_degen_watch",
                               return_value={"file": "x.png"}) as m:
            main.render_degen_watch_card({"match": "A vs B"}, date_str="2026-11-06")
        self.assertEqual(m.call_args.kwargs["date_str"], "2026-11-06")

    def test_weekend_multi_call_site_passes_run_date(self):
        src = open(os.path.join(os.path.dirname(__file__), "..", "scripts",
                                "generate_weekend_multi.py")).read()
        self.assertIn("render_multi_cards(anchor_pick, tier, legs, date_str=run_date)", src)


if __name__ == "__main__":
    unittest.main()
