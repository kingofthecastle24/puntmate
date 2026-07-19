"""Tests for the rewritten nightly results post (fresh-record reset,
2026-07-19). The old version posted 'All-time by personality' P&L from the
full ledger with '$10 flat stake' wording — both incompatible with the
fresh public record and with the staking-language ban."""

import json
import os
import shutil
import sys
import tempfile
import unittest

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "test-channel")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import post_results_telegram as prt
from copy_validator import validate_text, CopyValidationError


def _pick(date, result, bt="PUNTER_BET", match="A vs B", pick="A", odds=1.9):
    return {"date": date, "result": result, "bet_type": bt, "match": match, "pick": pick, "odds": odds}


class ResultsPostTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (prt.PICKS_PATH, prt.RECORD_START_PATH)
        prt.PICKS_PATH = os.path.join(self.tmp, "picks.json")
        prt.RECORD_START_PATH = os.path.join(self.tmp, "record_start_date")

    def tearDown(self):
        prt.PICKS_PATH, prt.RECORD_START_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, picks, start=None):
        with open(prt.PICKS_PATH, "w") as f:
            json.dump(picks, f)
        if start:
            with open(prt.RECORD_START_PATH, "w") as f:
                f.write(start)

    def test_pre_cutoff_picks_never_reach_the_public_post(self):
        self._write([
            _pick("2026-07-01", "loss", match="Old vs Stale"),
            _pick("2026-07-21", "win", match="New vs Fresh"),
        ], start="2026-07-20")
        text = prt.build_results_text(prt.load_record_picks())
        self.assertIn("New vs Fresh", text)
        self.assertNotIn("Old vs Stale", text)
        self.assertIn("Record: 1W–0L", text)

    def test_nothing_settled_on_fresh_record_returns_none(self):
        self._write([_pick("2026-07-01", "loss"), _pick("2026-07-21", "pending")], start="2026-07-20")
        self.assertIsNone(prt.build_results_text(prt.load_record_picks()))

    def test_no_staking_language_and_passes_copy_validator(self):
        self._write([_pick("2026-07-21", "win"), _pick("2026-07-22", "loss", bt="GAMBLER_BET")], start="2026-07-20")
        text = prt.build_results_text(prt.load_record_picks())
        self.assertNotIn("$", text)  # no dollar amounts at all
        self.assertNotIn("stake", text.lower())
        self.assertNotIn("All-time", text)
        try:
            validate_text(text, risk="STANDARD_PICK", public=True)
        except CopyValidationError as e:
            self.fail(f"results post failed copy validation: {e}")

    def test_tiers_grouped_by_bet_type_not_personality(self):
        self._write([
            _pick("2026-07-21", "win", bt="INVESTOR_BET"),
            _pick("2026-07-21", "loss", bt="GAMBLER_BET"),
            {"date": "2026-07-21", "result": "win", "personality": "punter",
             "match": "Legacy vs Row", "pick": "L", "odds": 1.5},  # no bet_type -> no tier line
        ], start="2026-07-20")
        text = prt.build_results_text(prt.load_record_picks())
        self.assertIn("Investor:* 1W–0L", text)
        self.assertIn("Gambler:* 0W–1L", text)
        self.assertIn("Record: 2W–1L", text)  # still counted overall


if __name__ == "__main__":
    unittest.main()
