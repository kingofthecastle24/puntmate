"""Tests for my_bets.py — Micah's personal flat-stake bet log and budget
tracker. Separate from the public ledger entirely; nothing here writes to
or reads result state from data/picks.json except compare_to_public_record's
deliberate, documented rescale for comparison purposes."""

import os
import sys
import json
import shutil
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import my_bets as mb


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


class MyBetsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (mb.REPO_ROOT, mb.CONFIG_PATH, mb.LOG_PATH, mb.REVIEW_ROOT, mb.PICKS_PATH)
        mb.REPO_ROOT = self.tmp
        mb.CONFIG_PATH = os.path.join(self.tmp, "config", "my_bets.json")
        mb.LOG_PATH = os.path.join(self.tmp, "data", "my_bets.json")
        mb.REVIEW_ROOT = os.path.join(self.tmp, "data", "review")
        mb.PICKS_PATH = os.path.join(self.tmp, "data", "picks.json")
        _write_json(mb.CONFIG_PATH, {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 100.0, "tab_balance": None})

    def tearDown(self):
        mb.REPO_ROOT, mb.CONFIG_PATH, mb.LOG_PATH, mb.REVIEW_ROOT, mb.PICKS_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_single_metadata(self, pick_id, **overrides):
        meta = {
            "has_pick": True,
            "pick_id": pick_id,
            "post_date": "2026-10-10",
            "match": "Warriors vs Storm",
            "sport": "rugbyleague_nrl",
            "sport_label": "NRL",
            "market": "Head to Head",
            "selection": "WARRIORS",
            "odds": "2.10",
            "bet_type_label": "BET TYPE: INVESTOR",
            "risk": "STANDARD_PICK",
            "confidence_label": "HIGH",
        }
        meta.update(overrides)
        _write_json(os.path.join(mb.REVIEW_ROOT, pick_id, "post-metadata.json"), meta)
        return meta

    def _write_multi_metadata(self, pick_id, tier, legs, **overrides):
        meta = {
            "has_pick": False,
            "is_weekend_multi": True,
            "pick_id": pick_id,
            "post_date": "2026-10-10",
            f"has_{tier}_multi": True,
            f"{tier}_multi_legs": legs,
        }
        meta.update(overrides)
        _write_json(os.path.join(mb.REVIEW_ROOT, pick_id, "post-metadata.json"), meta)
        return meta


class AddBetTests(MyBetsTestCase):
    def test_add_single_uses_config_stake_and_frozen_odds(self):
        self._write_single_metadata("2026-10-10_warriors-vs-storm")
        entry = mb.add_bet("2026-10-10_warriors-vs-storm")
        self.assertEqual(entry["type"], "single")
        self.assertEqual(entry["stake"], 2.0)
        self.assertEqual(entry["odds"], 2.10)
        self.assertEqual(entry["date"], "2026-10-10")
        self.assertEqual(entry["result"], "pending")
        self.assertIsNone(entry["pnl"])
        self.assertNotIn("tier", entry)
        self.assertEqual(mb.load_log(), [entry])

    def test_add_multi_uses_combined_odds_and_tier(self):
        legs = [
            {"match": "A vs B", "sport_key": "x", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "sport_key": "y", "selection": "D", "market": "Head to Head", "odds": "2.00"},
            {"match": "E vs F", "sport_key": "z", "selection": "E", "market": "Head to Head", "odds": "1.50"},
        ]
        self._write_multi_metadata("2026-10-10_weekend_multi", "punter", legs)
        entry = mb.add_bet("2026-10-10_weekend_multi", tier="punter")
        self.assertEqual(entry["type"], "multi")
        self.assertEqual(entry["tier"], "punter")
        self.assertEqual(entry["stake"], 5.0)
        self.assertEqual(entry["odds"], round(1.80 * 2.00 * 1.50, 2))

    def test_duplicate_add_is_rejected(self):
        self._write_single_metadata("2026-10-10_warriors-vs-storm")
        mb.add_bet("2026-10-10_warriors-vs-storm")
        with self.assertRaises(ValueError):
            mb.add_bet("2026-10-10_warriors-vs-storm")

    def test_single_without_tier_on_a_multi_only_pick_errors(self):
        self._write_multi_metadata("2026-10-10_weekend_multi", "punter", [
            {"match": "A vs B", "sport_key": "x", "selection": "A", "market": "Head to Head", "odds": "1.80"},
        ])
        with self.assertRaises(ValueError):
            mb.add_bet("2026-10-10_weekend_multi")  # has_pick is False -> needs --tier

    def test_tier_that_never_fired_errors(self):
        self._write_multi_metadata("2026-10-10_weekend_multi", "punter", [
            {"match": "A vs B", "sport_key": "x", "selection": "A", "market": "Head to Head", "odds": "1.80"},
        ])
        with self.assertRaises(ValueError):
            mb.add_bet("2026-10-10_weekend_multi", tier="gambler")

    def test_unknown_pick_id_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            mb.add_bet("2026-10-10_does-not-exist")


class ResolveSingleTests(MyBetsTestCase):
    def _scores(self, home, away, home_score, away_score):
        return [{
            "completed": True,
            "home_team": home,
            "away_team": away,
            "scores": [{"name": home, "score": home_score}, {"name": away, "score": away_score}],
        }]

    @patch("my_bets.fetch_scores")
    def test_single_h2h_win(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm", selection="WARRIORS", market="Head to Head")
        mb.add_bet("p1")
        mock_fetch.return_value = self._scores("Warriors", "Storm", 24, 12)
        resolved = mb.resolve_pending()
        self.assertEqual(resolved, 1)
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "win")
        self.assertAlmostEqual(entry["pnl"], 2.0 * (2.10 - 1), places=2)

    @patch("my_bets.fetch_scores")
    def test_single_loss(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm", selection="WARRIORS", market="Head to Head")
        mb.add_bet("p1")
        mock_fetch.return_value = self._scores("Warriors", "Storm", 10, 30)
        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "loss")
        self.assertEqual(entry["pnl"], -2.0)

    @patch("my_bets.fetch_scores")
    def test_single_total_push(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm", selection="UNDER 7", market="Total", odds="2.00")
        mb.add_bet("p1")
        mock_fetch.return_value = self._scores("Warriors", "Storm", 4, 3)
        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "push")
        self.assertEqual(entry["pnl"], 0.0)

    @patch("my_bets.fetch_scores")
    def test_single_handicap_is_manual_never_guessed(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm", selection="WARRIORS -6.5", market="Handicap")
        mb.add_bet("p1")
        mock_fetch.return_value = self._scores("Warriors", "Storm", 24, 12)
        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "manual")
        self.assertIsNone(entry["pnl"])

    @patch("my_bets.fetch_scores")
    def test_no_matching_score_stays_pending(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm")
        mb.add_bet("p1")
        mock_fetch.return_value = []
        resolved = mb.resolve_pending()
        self.assertEqual(resolved, 0)
        self.assertEqual(mb.load_log()[0]["result"], "pending")

    @patch("my_bets.fetch_scores")
    def test_stale_pending_becomes_unresolved(self, mock_fetch):
        self._write_single_metadata("p1", match="Warriors vs Storm", post_date="2020-01-01")
        entry = mb.add_bet("p1")
        self.assertEqual(entry["date"], "2020-01-01")
        mock_fetch.return_value = []
        resolved = mb.resolve_pending(stale_days=5)
        self.assertEqual(resolved, 1)
        self.assertEqual(mb.load_log()[0]["result"], "unresolved")
        self.assertIsNone(mb.load_log()[0]["pnl"])


class ResolveMultiTests(MyBetsTestCase):
    def _scores(self, home, away, home_score, away_score):
        return [{
            "completed": True,
            "home_team": home,
            "away_team": away,
            "scores": [{"name": home, "score": home_score}, {"name": away, "score": away_score}],
        }]

    @patch("my_bets.fetch_scores")
    def test_all_legs_win_is_a_multi_win(self, mock_fetch):
        legs = [
            {"match": "A vs B", "sport_key": "sport1", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "sport_key": "sport2", "selection": "C", "market": "Head to Head", "odds": "2.00"},
            {"match": "E vs F", "sport_key": "sport3", "selection": "E", "market": "Head to Head", "odds": "1.50"},
        ]
        self._write_multi_metadata("wk1", "punter", legs)
        mb.add_bet("wk1", tier="punter")

        def fake_fetch(sport_key, **kw):
            return {
                "sport1": self._scores("A", "B", 10, 2),
                "sport2": self._scores("C", "D", 10, 2),
                "sport3": self._scores("E", "F", 10, 2),
            }[sport_key]
        mock_fetch.side_effect = fake_fetch

        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "win")
        combined = 1.80 * 2.00 * 1.50
        self.assertAlmostEqual(entry["pnl"], 5.0 * (combined - 1), places=2)

    @patch("my_bets.fetch_scores")
    def test_any_leg_loss_is_a_multi_loss_even_if_others_still_pending(self, mock_fetch):
        legs = [
            {"match": "A vs B", "sport_key": "sport1", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "sport_key": "sport2", "selection": "C", "market": "Head to Head", "odds": "2.00"},
        ]
        self._write_multi_metadata("wk1", "punter", legs)
        mb.add_bet("wk1", tier="punter")

        def fake_fetch(sport_key, **kw):
            if sport_key == "sport1":
                return self._scores("A", "B", 2, 10)  # A loses
            return []  # sport2 not finished yet
        mock_fetch.side_effect = fake_fetch

        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "loss")
        self.assertEqual(entry["pnl"], -5.0)

    @patch("my_bets.fetch_scores")
    def test_push_leg_does_not_block_a_win(self, mock_fetch):
        legs = [
            {"match": "A vs B", "sport_key": "sport1", "selection": "UNDER 7", "market": "Total", "odds": "1.80"},
            {"match": "C vs D", "sport_key": "sport2", "selection": "C", "market": "Head to Head", "odds": "2.00"},
        ]
        self._write_multi_metadata("wk1", "punter", legs)
        mb.add_bet("wk1", tier="punter")

        def fake_fetch(sport_key, **kw):
            if sport_key == "sport1":
                return self._scores("A", "B", 4, 3)  # total=7 -> push
            return self._scores("C", "D", 10, 2)  # C wins
        mock_fetch.side_effect = fake_fetch

        mb.resolve_pending()
        entry = mb.load_log()[0]
        self.assertEqual(entry["result"], "win")

    @patch("my_bets.fetch_scores")
    def test_handicap_leg_blocks_win_verdict_until_a_loss_or_manual_check(self, mock_fetch):
        legs = [
            {"match": "A vs B", "sport_key": "sport1", "selection": "A -6.5", "market": "Handicap", "odds": "1.80"},
            {"match": "C vs D", "sport_key": "sport2", "selection": "C", "market": "Head to Head", "odds": "2.00"},
        ]
        self._write_multi_metadata("wk1", "punter", legs)
        mb.add_bet("wk1", tier="punter")
        mock_fetch.return_value = self._scores("A", "B", 10, 2)

        resolved = mb.resolve_pending()
        self.assertEqual(resolved, 0)
        self.assertEqual(mb.load_log()[0]["result"], "pending")


class SummaryTests(MyBetsTestCase):
    def test_monthly_summary_computes_staked_returned_net(self):
        mb.save_log([
            {"pick_id": "a", "type": "single", "date": "2026-10-01", "stake": 2.0, "odds": 2.0, "result": "win", "pnl": 2.0},
            {"pick_id": "b", "type": "single", "date": "2026-10-02", "stake": 2.0, "odds": 1.5, "result": "loss", "pnl": -2.0},
        ])
        s = mb.monthly_summary("2026-10")
        self.assertEqual(s["staked"], 4.0)
        self.assertEqual(s["returned"], 4.0)  # win leg: stake*odds = 2*2
        self.assertEqual(s["net"], 0.0)

    def test_warns_when_gross_staked_exceeds_budget(self):
        _write_json(mb.CONFIG_PATH, {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 10.0, "tab_balance": None})
        entries = [{"pick_id": f"p{i}", "type": "single", "date": "2026-10-01", "stake": 5.0, "odds": 1.5, "result": "pending", "pnl": None} for i in range(3)]
        mb.save_log(entries)
        lines = mb.monthly_summary_lines("2026-10")
        self.assertTrue(any("over your $10.00 budget" in l for l in lines))

    def test_warns_separately_when_net_loss_exceeds_budget(self):
        _write_json(mb.CONFIG_PATH, {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 5.0, "tab_balance": None})
        mb.save_log([{"pick_id": "a", "type": "single", "date": "2026-10-01", "stake": 6.0, "odds": 1.5, "result": "loss", "pnl": -6.0}])
        lines = mb.monthly_summary_lines("2026-10")
        self.assertTrue(any("Net loss" in l for l in lines))

    def test_tab_balance_shown_when_set(self):
        _write_json(mb.CONFIG_PATH, {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 100.0, "tab_balance": 42.5})
        mb.save_log([])
        lines = mb.monthly_summary_lines("2026-10")
        self.assertTrue(any("TAB balance: $42.50" in l for l in lines))

    def test_compare_to_public_record_rescales_linearly(self):
        _write_json(mb.PICKS_PATH, [
            {"pnl": 10.0, "result": "win"},   # win at $10 flat stake
            {"pnl": -10.0, "result": "loss"},  # loss at $10 flat stake
        ])
        mb.save_log([{"pick_id": "a", "type": "single", "date": "2026-10-01", "stake": 2.0, "odds": 2.0, "result": "win", "pnl": 2.0}])
        cmp = mb.compare_to_public_record()
        # public net pnl is 0 at $10 stake -> still 0 once rescaled to $2
        self.assertEqual(cmp["published_record_pnl_at_my_scale"], 0.0)
        self.assertEqual(cmp["my_staked"], 2.0)
        self.assertEqual(cmp["my_pnl"], 2.0)


if __name__ == "__main__":
    unittest.main()
