"""Tests for owner_dm.py — the private Telegram DM mirroring every public
pick/multi PuntMate actually publishes, at Micah's own flat stakes. Never
regenerates copy (reads the frozen post-metadata.json); never sent on a
No-Bet/Watchlist day; staking language is fine here (private DM only) and
this text never touches copy_validator."""

import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import owner_dm as odm
import my_bets as mb


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class BuildSingleDmTests(unittest.TestCase):
    def test_includes_match_selection_odds_type_risk_confidence_and_stake(self):
        metadata = {
            "match": "Warriors vs Storm",
            "sport_label": "NRL",
            "selection": "WARRIORS",
            "odds": "2.10",
            "market": "Head to Head",
            "bet_type_label": "BET TYPE: INVESTOR",
            "risk": "STANDARD_PICK",
            "confidence_label": "HIGH",
        }
        text = odm.build_single_dm(metadata, 2.0)
        for expected in ("Warriors vs Storm", "WARRIORS", "2.10", "Head to Head",
                          "BET TYPE: INVESTOR", "STANDARD_PICK", "HIGH", "$2.00"):
            self.assertIn(expected, text)

    def test_private_banner_present(self):
        text = odm.build_single_dm({"match": "A vs B"}, 2.0)
        self.assertIn("PRIVATE", text)

    def test_bet_type_label_prefix_is_never_doubled(self):
        """bet_type_label already reads 'BET TYPE: INVESTOR' (see
        generate_pick.BET_TYPE_LABELS) — regression for a real bug caught in
        the dry run where the template added its own 'BET TYPE: ' on top."""
        text = odm.build_single_dm({"match": "A vs B", "bet_type_label": "BET TYPE: INVESTOR"}, 2.0)
        self.assertIn("BET TYPE: INVESTOR", text)
        self.assertNotIn("BET TYPE: BET TYPE:", text)

    def test_bet_type_falls_back_to_raw_bet_type_with_one_prefix(self):
        text = odm.build_single_dm({"match": "A vs B", "bet_type": "PUNTER_BET"}, 2.0)
        self.assertIn("BET TYPE: PUNTER_BET", text)
        self.assertNotIn("BET TYPE: BET TYPE:", text)


class BuildMultiDmTests(unittest.TestCase):
    def test_includes_every_leg_combined_odds_tier_and_stake(self):
        legs = [
            {"match": "A vs B", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "selection": "D", "market": "Total", "odds": "2.00"},
            {"match": "E vs F", "selection": "E -6.5", "market": "Handicap", "odds": "1.50"},
        ]
        text = odm.build_multi_dm("punter", legs, 5.0)
        self.assertIn("PUNTER MULTI", text)
        self.assertIn("Leg 1: A vs B", text)
        self.assertIn("Leg 2: C vs D", text)
        self.assertIn("Leg 3: E vs F", text)
        combined = 1.80 * 2.00 * 1.50
        self.assertIn(f"{combined:.2f}", text)
        self.assertIn("$5.00", text)

    def test_gambler_tier_label(self):
        legs = [
            {"match": "A vs B", "selection": "A", "market": "Head to Head", "odds": "3.0"},
            {"match": "C vs D", "selection": "D", "market": "Head to Head", "odds": "3.0"},
            {"match": "E vs F", "selection": "E", "market": "Head to Head", "odds": "3.0"},
        ]
        text = odm.build_multi_dm("gambler", legs, 5.0)
        self.assertIn("GAMBLER MULTI", text)


class OwnerDmMainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._odm_orig = (odm.REPO_ROOT, odm.REVIEW_ROOT, odm.DRY_RUN)
        odm.REPO_ROOT = self.tmp
        odm.REVIEW_ROOT = os.path.join(self.tmp, "data", "review")
        odm.DRY_RUN = True
        self._mb_orig = (mb.REPO_ROOT, mb.CONFIG_PATH, mb.LOG_PATH, mb.REVIEW_ROOT, mb.PICKS_PATH)
        mb.REPO_ROOT = self.tmp
        mb.CONFIG_PATH = os.path.join(self.tmp, "config", "my_bets.json")
        mb.LOG_PATH = os.path.join(self.tmp, "data", "my_bets.json")
        mb.REVIEW_ROOT = odm.REVIEW_ROOT
        mb.PICKS_PATH = os.path.join(self.tmp, "data", "picks.json")
        _write_json(mb.CONFIG_PATH, {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 100.0, "tab_balance": None})
        _write_json(mb.LOG_PATH, [])

    def tearDown(self):
        odm.REPO_ROOT, odm.REVIEW_ROOT, odm.DRY_RUN = self._odm_orig
        mb.REPO_ROOT, mb.CONFIG_PATH, mb.LOG_PATH, mb.REVIEW_ROOT, mb.PICKS_PATH = self._mb_orig
        os.environ.pop("PICK_ID", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_metadata(self, pick_id, metadata):
        _write_json(os.path.join(odm.REVIEW_ROOT, pick_id, "post-metadata.json"), metadata)

    def test_sends_one_dm_for_a_single_pick(self):
        pick_id = "2026-10-10_warriors-vs-storm"
        self._write_metadata(pick_id, {
            "has_pick": True, "match": "Warriors vs Storm", "sport_label": "NRL",
            "selection": "WARRIORS", "odds": "2.10", "market": "Head to Head",
            "bet_type_label": "BET TYPE: INVESTOR", "risk": "STANDARD_PICK", "confidence_label": "HIGH",
        })
        os.environ["PICK_ID"] = pick_id
        with patch("owner_dm._send") as mock_send:
            mock_send.return_value = {"ok": True, "dry_run": True}
            odm.main()
            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]
        self.assertIn("WARRIORS", sent_text)
        self.assertIn("This month", sent_text)

    def test_sends_a_dm_per_fired_multi_tier(self):
        pick_id = "2026-10-10_weekend_multi"
        legs = [
            {"match": "A vs B", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "selection": "C", "market": "Head to Head", "odds": "2.00"},
            {"match": "E vs F", "selection": "E", "market": "Head to Head", "odds": "1.50"},
        ]
        self._write_metadata(pick_id, {
            "has_pick": False, "is_weekend_multi": True,
            "has_punter_multi": True, "punter_multi_legs": legs,
            "has_gambler_multi": True, "gambler_multi_legs": legs,
        })
        os.environ["PICK_ID"] = pick_id
        with patch("owner_dm._send") as mock_send:
            mock_send.return_value = {"ok": True, "dry_run": True}
            odm.main()
            self.assertEqual(mock_send.call_count, 2)

    def test_no_bet_day_sends_nothing(self):
        pick_id = "2026-10-10_no-bet"
        self._write_metadata(pick_id, {"has_pick": False})
        os.environ["PICK_ID"] = pick_id
        with patch("owner_dm._send") as mock_send:
            odm.main()
            mock_send.assert_not_called()

    def test_watchlist_day_sends_nothing(self):
        pick_id = "2026-10-10_no-bet"
        self._write_metadata(pick_id, {"has_pick": False, "has_watchlist": True, "watchlist": [{"match": "A vs B"}]})
        os.environ["PICK_ID"] = pick_id
        with patch("owner_dm._send") as mock_send:
            odm.main()
            mock_send.assert_not_called()

    def test_missing_pick_id_sends_nothing(self):
        os.environ.pop("PICK_ID", None)
        with patch("owner_dm._send") as mock_send:
            odm.main()
            mock_send.assert_not_called()

    def test_dry_run_prints_instead_of_calling_telegram(self):
        pick_id = "2026-10-10_warriors-vs-storm"
        self._write_metadata(pick_id, {
            "has_pick": True, "match": "Warriors vs Storm", "sport_label": "NRL",
            "selection": "WARRIORS", "odds": "2.10", "market": "Head to Head",
        })
        os.environ["PICK_ID"] = pick_id
        odm.DRY_RUN = True
        with patch("owner_dm.requests.post") as mock_post:
            odm.main()
            mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
