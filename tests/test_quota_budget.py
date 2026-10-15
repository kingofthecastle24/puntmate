"""
Tests for quota_budget.py (2026-10-15 redesign). Run #206 burned the
account's full 500/500 free-tier credits by scanning every registered
sport on every run; this module's whole job is to make that structurally
impossible again — every paid call reserves first, and a reservation is
refused whenever the effective allowance is unknown or exhausted.
"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import quota_budget as qb


class QuotaBudgetTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_path = qb.BUDGET_PATH
        qb.BUDGET_PATH = os.path.join(self._tmpdir.name, "quota_budget.json")
        self.period = "2026-11-01T00:00:00+00:00"
        self.reset = "2026-12-01T00:00:00+00:00"

    def tearDown(self):
        qb.BUDGET_PATH = self._orig_path
        self._tmpdir.cleanup()

    # ---- basic lifecycle ----

    def test_reserve_fails_closed_when_period_does_not_exist(self):
        self.assertIsNone(qb.reserve(self.period, qb.ODDS, 6))

    def test_reserve_fails_closed_when_provider_remaining_unknown(self):
        qb.init_exhausted_period(self.period, self.reset)
        # init_exhausted_period deliberately seeds provider_remaining=0 and
        # fully-charged buckets, so this exercises the "exhausted" path --
        # confirm a genuinely fresh, un-synced period also fails closed.
        fresh_period = "2026-12-01T00:00:00+00:00"
        data = qb._load_all()
        data["periods"][fresh_period] = qb._empty_period(fresh_period, "2027-01-01T00:00:00+00:00")
        qb._save_all(data)
        self.assertIsNone(qb.reserve(fresh_period, qb.ODDS, 6))

    def test_reserve_succeeds_once_provider_remaining_is_synced(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6, note="daily scan")
        self.assertIsNotNone(rid)

    def test_reserve_respects_local_bucket_limit_even_if_provider_has_more(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=10000)
        # ODDS bucket's local limit is 336 (DEFAULT_LIMITS) -- provider
        # headroom alone must never let a reservation exceed the local cap.
        rid = qb.reserve(self.period, qb.ODDS, 337)
        self.assertIsNone(rid)
        rid2 = qb.reserve(self.period, qb.ODDS, 336)
        self.assertIsNotNone(rid2)

    def test_confirm_moves_reservation_into_charged(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6)
        qb.confirm(self.period, rid)
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["charged"], 6)
        self.assertEqual(rec["buckets"][qb.ODDS]["reserved_total"], 0)
        self.assertEqual(rec["reservations"][rid]["status"], qb.CONFIRMED)

    def test_confirm_with_different_actual_amount(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6)
        qb.confirm(self.period, rid, actual_amount=3)
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["charged"], 3)

    def test_release_gives_credits_back(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6)
        qb.release(self.period, rid)
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["reserved_total"], 0)
        self.assertEqual(rec["buckets"][qb.ODDS]["charged"], 0)
        self.assertEqual(qb.effective_remaining(self.period, qb.ODDS), 336)

    def test_mark_uncertain_keeps_the_charge_not_a_guessed_release(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6)
        qb.mark_uncertain(self.period, rid)
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["charged"], 6)
        self.assertEqual(rec["reservations"][rid]["status"], qb.UNCERTAIN)

    def test_double_resolution_is_a_noop(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        rid = qb.reserve(self.period, qb.ODDS, 6)
        qb.confirm(self.period, rid)
        qb.confirm(self.period, rid)  # must not double-charge
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["charged"], 6)

    # ---- October-inherited exhaustion ----

    def test_init_exhausted_period_blocks_every_reservation(self):
        qb.init_exhausted_period(self.period, self.reset)
        self.assertIsNone(qb.reserve(self.period, qb.ODDS, 1))
        self.assertIsNone(qb.reserve(self.period, qb.SCORES, 1))

    def test_init_exhausted_period_is_idempotent_and_never_overwrites(self):
        qb.init_exhausted_period(self.period, self.reset)
        rid = None
        qb.start_new_period  # (no-op reference, just documenting intent below)
        data_before = qb._load_all()
        qb.init_exhausted_period(self.period, self.reset)  # second call
        data_after = qb._load_all()
        self.assertEqual(data_before, data_after)

    # ---- provider header reconciliation ----

    def test_reconcile_provider_headers_updates_remaining(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        qb.reconcile_provider_headers(self.period, remaining="494", used="6")
        rec = qb.get_period(self.period)
        self.assertEqual(rec["provider_remaining"], 494)

    def test_reconcile_with_non_numeric_remaining_does_not_crash_or_corrupt(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        qb.reconcile_provider_headers(self.period, remaining="unknown")
        rec = qb.get_period(self.period)
        self.assertEqual(rec["provider_remaining"], 500)  # left as prior value

    def test_effective_remaining_is_the_tighter_of_local_and_provider(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        qb.reconcile_provider_headers(self.period, remaining="4")
        # provider now says only 4 left, even though the local ODDS bucket
        # has 336 of headroom -- the tighter number wins.
        self.assertEqual(qb.effective_remaining(self.period, qb.ODDS), 4)

    # ---- start_new_period requires confirmation ----

    def test_start_new_period_requires_a_confirmed_remaining_count(self):
        with self.assertRaises(ValueError):
            qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=None)

    def test_start_new_period_is_idempotent(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        qb.reserve(self.period, qb.ODDS, 6)
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=999)
        # second call must not reset reservation history
        rec = qb.get_period(self.period)
        self.assertEqual(rec["buckets"][qb.ODDS]["reserved_total"], 6)

    def test_persists_across_reloads(self):
        qb.start_new_period(self.period, self.reset, confirmed_provider_remaining=500)
        qb.reserve(self.period, qb.ODDS, 6)
        with open(qb.BUDGET_PATH) as f:
            on_disk = json.load(f)
        self.assertIn(self.period, on_disk["periods"])
        self.assertEqual(on_disk["periods"][self.period]["buckets"][qb.ODDS]["reserved_total"], 6)


if __name__ == "__main__":
    unittest.main()
