"""Tests for challenge_tracker.py — the public $100 -> $1,000 challenge.

The challenge is Phase 2 of the growth plan: a notional, publicly tracked
balance following PuntMate's own posted picks. Key guarantees under test:
disabled by default, idempotent (a pick never counts twice), deterministic
10%-of-balance progression, honest bust/complete handling, and a public
recap line that never uses staking language (copy_validator compliance).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import challenge_tracker as ct
from copy_validator import validate_text, CopyValidationError


def _pick(pid, date, result, odds, match="Team A vs Team B"):
    return {"id": pid, "date": date, "result": result, "odds": odds,
            "match": match, "pick": "Team A"}


class ChallengeTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (ct.CONFIG_PATH, ct.LEDGER_PATH, ct.PICKS_PATH)
        ct.CONFIG_PATH = os.path.join(self.tmp, "challenge_config.json")
        ct.LEDGER_PATH = os.path.join(self.tmp, "challenge.json")
        ct.PICKS_PATH = os.path.join(self.tmp, "picks.json")

    def tearDown(self):
        ct.CONFIG_PATH, ct.LEDGER_PATH, ct.PICKS_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_config(self, **overrides):
        cfg = {"enabled": True, "start_balance": 100.0, "goal": 1000.0}
        cfg.update(overrides)
        with open(ct.CONFIG_PATH, "w") as f:
            json.dump(cfg, f)
        return cfg

    def test_disabled_by_default_is_a_noop(self):
        self._write_config(enabled=False)
        self.assertIsNone(ct.apply_settled_picks())
        self.assertFalse(os.path.exists(ct.LEDGER_PATH))
        self.assertEqual(ct.public_line(), "")

    def test_first_run_stamps_start_date_and_ignores_older_picks(self):
        self._write_config()
        picks = [_pick("old1", "2026-01-01", "win", 2.0)]
        ledger = ct.apply_settled_picks(picks=picks)
        cfg = json.load(open(ct.CONFIG_PATH))
        self.assertIn("started", cfg)
        # the old pick predates the start date -> untouched balance
        self.assertEqual(ledger["balance"], 100.0)
        self.assertEqual(ledger["picks_applied"], 0)

    def test_win_and_loss_progression_at_ten_percent(self):
        self._write_config(started="2026-07-01")
        picks = [
            _pick("p1", "2026-07-02", "win", 1.80),   # stake 10.00, +8.00 -> 108.00
            _pick("p2", "2026-07-03", "loss", 2.10),  # stake 10.80, -10.80 -> 97.20
            _pick("p3", "2026-07-04", "push", 1.90),  # no change
        ]
        ledger = ct.apply_settled_picks(picks=picks)
        self.assertEqual(ledger["balance"], 97.20)
        self.assertEqual(ledger["picks_applied"], 3)
        self.assertEqual(ledger["history"][0]["balance_after"], 108.00)
        self.assertEqual(ledger["history"][2]["pnl"], 0.0)

    def test_idempotent_reruns_never_double_count(self):
        self._write_config(started="2026-07-01")
        picks = [_pick("p1", "2026-07-02", "win", 2.0)]
        first = ct.apply_settled_picks(picks=picks)
        second = ct.apply_settled_picks(picks=picks)
        self.assertEqual(first["balance"], second["balance"])
        self.assertEqual(second["picks_applied"], 1)

    def test_pending_and_manual_results_are_ignored(self):
        self._write_config(started="2026-07-01")
        picks = [
            _pick("p1", "2026-07-02", "pending", 2.0),
            _pick("p2", "2026-07-02", "manual", 2.0),
            {"id": "p3", "date": "2026-07-02", "result": None, "odds": 2.0, "match": "X vs Y", "pick": "X"},
        ]
        ledger = ct.apply_settled_picks(picks=picks)
        self.assertEqual(ledger["picks_applied"], 0)
        self.assertEqual(ledger["balance"], 100.0)

    def test_goal_reached_completes_and_freezes(self):
        self._write_config(started="2026-07-01", start_balance=900.0)
        picks = [
            _pick("p1", "2026-07-02", "win", 3.0),   # stake 90, +180 -> 1080 -> complete
            _pick("p2", "2026-07-03", "loss", 2.0),  # must NOT apply
        ]
        ledger = ct.apply_settled_picks(picks=picks)
        self.assertEqual(ledger["status"], "complete")
        self.assertEqual(ledger["picks_applied"], 1)
        self.assertEqual(ledger["balance"], 1080.0)

    def test_bust_stays_on_the_record(self):
        self._write_config(started="2026-07-01", start_balance=1.05)
        picks = [_pick("p1", "2026-07-02", "loss", 2.0)]  # stake 0.11 -> 0.94 < $1
        ledger = ct.apply_settled_picks(picks=picks)
        self.assertEqual(ledger["status"], "busted")
        # re-running with more picks applies nothing
        ledger = ct.apply_settled_picks(picks=picks + [_pick("p2", "2026-07-03", "win", 5.0)])
        self.assertEqual(ledger["picks_applied"], 1)

    def test_public_line_passes_copy_validator_in_all_states(self):
        """The recap line is public copy — it must clear the same validator
        every post does (no staking language, no 'bankroll')."""
        self._write_config(started="2026-07-01")
        for picks, _label in [
            ([_pick("p1", "2026-07-02", "win", 2.0)], "running"),
            ([_pick("p2", "2026-07-03", "win", 12.0)], "complete"),
        ]:
            ledger = ct.apply_settled_picks(picks=picks)
            line = ct.public_line(ledger)
            self.assertTrue(line)
            try:
                validate_text(line, risk="STANDARD_PICK", public=True)
            except CopyValidationError as e:
                self.fail(f"challenge public line failed copy validation: {e}")

    def test_public_line_empty_until_first_pick_applied(self):
        self._write_config(started="2026-07-01")
        ct.apply_settled_picks(picks=[])
        self.assertEqual(ct.public_line(), "")


if __name__ == "__main__":
    unittest.main()
