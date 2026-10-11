"""Tests for owner_dm.py -- the private owner DM + month budget figures.

Key guarantees under test: the DM is built from the SAME published data (never
regenerated), only bets whose public Telegram post succeeded get a DM, budget
problems only ever produce warnings (nothing is skipped), and a DM failure can
never raise into publishing."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import owner_dm
from set_multi_result import set_result

CFG = {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 100.0}

MULTI_TEXT = (
    "*🎯 PUNTMATE NZ — THE PUNTER'S MULTI*\n\n"
    "*Leg 1:* A vs B — A @ 1.50 (Head to Head)\n"
    "*Leg 2:* C vs D — D @ 2.00 (Head to Head)\n\n"
    "*Combined: 3.00*\n*BET TYPE: PUNTER*\n"
)


def _write(path, data, raw=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(data if raw else json.dumps(data))


def make_repo(root, singles=(), multis=(), ledger=(), multi_results=None):
    """singles: (pick_id, date, match, odds, telegram_ok); multis: (pick_id,
    date, tier, telegram_ok); ledger: picks.json rows."""
    _write(os.path.join(root, "data", "picks.json"), list(ledger))
    if multi_results is not None:
        _write(os.path.join(root, "data", "multi_results.json"), multi_results)
    for pid, date, match, odds, ok in singles:
        _write(os.path.join(root, "data", "published", f"{pid}.json"), {"telegram": {"ok": ok}})
        _write(os.path.join(root, "data", "review", pid, "post-metadata.json"),
               {"has_pick": True, "pick_id": pid, "post_date": date, "match": match,
                "selection": "TEAM A", "market": "Head to Head", "odds": str(odds),
                "bet_type": "PUNTER_BET", "risk": "RISKY_PICK", "confidence": "LOW"})
    for pid, date, tier, ok in multis:
        _write(os.path.join(root, "data", "published", f"{pid}.json"),
               {f"telegram_{tier}_multi": {"ok": ok}})
        _write(os.path.join(root, "data", "review", pid, "post-metadata.json"),
               {"has_pick": False, "is_weekend_multi": True, "pick_id": pid,
                "post_date": date, f"has_{tier}_multi": True})
        _write(os.path.join(root, "data", "review", pid, f"{tier}-multi-post.txt"),
               MULTI_TEXT, raw=True)


class HelperTests(unittest.TestCase):
    def test_defaults_when_config_missing(self):
        self.assertEqual(owner_dm.load_config("/nonexistent/x.json"), CFG)

    def test_norm_result(self):
        self.assertEqual(owner_dm.norm_result("WIN"), "win")
        self.assertEqual(owner_dm.norm_result("void"), "push")
        for r in ("pending", "manual", "unresolved", None, ""):
            self.assertEqual(owner_dm.norm_result(r), "open")

    def test_parse_multi(self):
        legs, combined = owner_dm.parse_multi(MULTI_TEXT)
        self.assertEqual(len(legs), 2)
        self.assertTrue(legs[0].startswith("Leg 1: A vs B"))
        self.assertNotIn("*", legs[0])
        self.assertEqual(combined, 3.0)

    def test_parse_multi_missing_combined(self):
        self.assertEqual(owner_dm.parse_multi("nothing here"), ([], None))


class StatsTests(unittest.TestCase):
    def test_win_loss_push_open_net(self):
        items = [
            {"id": "a", "kind": "single", "stake": 2.0, "odds": 1.6, "result": "win"},   # +3.20 back
            {"id": "b", "kind": "single", "stake": 2.0, "odds": 2.0, "result": "loss"},  # 0 back
            {"id": "c", "kind": "single", "stake": 2.0, "odds": 2.0, "result": "push"},  # 2.00 back
            {"id": "d", "kind": "single", "stake": 2.0, "odds": 2.0, "result": "open"},
        ]
        s = owner_dm.month_stats(items, CFG)
        self.assertAlmostEqual(s["staked"], 8.0)
        self.assertAlmostEqual(s["returned"], 5.2)
        self.assertAlmostEqual(s["net"], 5.2 - 6.0)
        self.assertEqual(s["open_count"], 1)
        self.assertAlmostEqual(s["open_stake"], 2.0)
        self.assertEqual(s["warnings"], [])

    def test_gross_budget_warning_only(self):
        items = [{"id": str(i), "kind": "single", "stake": 2.0, "odds": 1.5, "result": "open"}
                 for i in range(51)]  # $102 staked
        s = owner_dm.month_stats(items, CFG)
        self.assertEqual(len(s["warnings"]), 1)
        self.assertIn("over your $100.00 monthly budget", s["warnings"][0])
        self.assertLess(s["left"], 0)

    def test_net_loss_warning(self):
        items = [{"id": str(i), "kind": "multi", "stake": 5.0, "odds": 3.0, "result": "loss"}
                 for i in range(21)]  # $105 lost
        s = owner_dm.month_stats(items, CFG)
        self.assertTrue(any("Net loss" in w for w in s["warnings"]))

    def test_with_current_dedupes(self):
        base = [{"id": "x", "kind": "single", "stake": 2.0, "odds": 1.5, "result": "win"}]
        cur = [{"id": "x", "kind": "single", "stake": 2.0, "odds": 1.5, "result": "open"},
               {"id": "y", "kind": "single", "stake": 2.0, "odds": 1.5, "result": "open"}]
        merged = owner_dm.with_current(base, cur)
        self.assertEqual([i["id"] for i in merged], ["x", "y"])
        self.assertEqual(merged[0]["result"], "win")  # existing record wins


class CollectTests(unittest.TestCase):
    def test_only_telegram_ok_and_this_month_and_results(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(
                root,
                singles=[
                    ("2026-10-05_A_vs_B", "2026-10-05", "A vs B", 1.6, True),
                    ("2026-10-06_C_vs_D", "2026-10-06", "C vs D", 2.0, False),  # public post failed
                    ("2026-09-30_E_vs_F", "2026-09-30", "E vs F", 2.0, True),   # last month
                ],
                multis=[("2026-10-01_weekend_multi", "2026-10-01", "punter", True)],
                ledger=[{"date": "2026-10-05", "match": "A vs B", "result": "win"}],
                multi_results={"2026-10-01_weekend_multi": {"punter": "loss"}},
            )
            items = owner_dm.collect_items("2026-10", root, CFG)
            by_id = {i["id"]: i for i in items}
            self.assertEqual(set(by_id), {"2026-10-05_A_vs_B", "2026-10-01_weekend_multi:punter"})
            self.assertEqual(by_id["2026-10-05_A_vs_B"]["result"], "win")
            self.assertEqual(by_id["2026-10-05_A_vs_B"]["stake"], 2.0)
            multi = by_id["2026-10-01_weekend_multi:punter"]
            self.assertEqual((multi["stake"], multi["odds"], multi["result"]), (5.0, 3.0, "loss"))

    def test_no_published_dir_is_empty(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(owner_dm.collect_items("2026-10", root, CFG), [])


class NotifyTests(unittest.TestCase):
    def _meta_single(self):
        return {"has_pick": True, "pick_id": "2026-10-09_A_vs_B", "post_date": "2026-10-09",
                "match": "A vs B", "selection": "TEAM A", "market": "Head to Head",
                "odds": "1.60", "bet_type": "PUNTER_BET", "risk": "RISKY_PICK",
                "confidence": "LOW"}

    def test_single_dm_sent_only_when_public_telegram_ok(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            sent = []
            owner_dm.notify(self._meta_single(), root, {"telegram": {"ok": False}},
                            ["telegram"], send=sent.append, repo_root=root)
            self.assertEqual(sent, [])
            owner_dm.notify(self._meta_single(), root, {"telegram": {"ok": True}},
                            ["telegram"], send=sent.append, repo_root=root)
            self.assertEqual(len(sent), 1)
            text = sent[0]
            self.assertIn("follow at $2.00", text)
            self.assertIn("TEAM A (Head to Head) @ 1.60", text)
            self.assertIn("returns $3.20 if it wins", text)
            self.assertIn("Staked $2.00 of $100.00 budget", text)  # current bet counted once

    def test_no_dm_when_telegram_not_an_intended_platform(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            sent = []
            owner_dm.notify(self._meta_single(), root, {"telegram": {"ok": True}},
                            ["instagram_feed"], send=sent.append, repo_root=root)
            self.assertEqual(sent, [])

    def test_multi_dm_per_tier_and_counted_once(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            pid = "2026-10-01_weekend_multi"
            _write(os.path.join(root, "data", "review", pid, "punter-multi-post.txt"),
                   MULTI_TEXT, raw=True)
            meta = {"has_pick": False, "is_weekend_multi": True, "pick_id": pid,
                    "post_date": "2026-10-01", "has_punter_multi": True,
                    "has_gambler_multi": True}  # gambler flagged but its post failed
            results = {"telegram_punter_multi": {"ok": True},
                       "telegram_gambler_multi": {"ok": False}}
            sent = []
            review_dir = os.path.join(root, "data", "review", pid)
            owner_dm.notify(meta, review_dir, results, ["telegram"], send=sent.append, repo_root=root)
            self.assertEqual(len(sent), 1)
            self.assertIn("Punter multi: follow at $5.00", sent[0])
            self.assertIn("Combined: 3.00", sent[0])
            self.assertIn("returns $15.00 if every leg wins", sent[0])
            self.assertIn("Staked $5.00 of $100.00 budget", sent[0])

    def test_dry_run_prints_and_never_sends(self):
        with tempfile.TemporaryDirectory() as root:
            make_repo(root)
            sent = []
            out = owner_dm.notify(self._meta_single(), root, {}, ["telegram"],
                                  send=sent.append, repo_root=root, dry=True)
            self.assertEqual(len(out), 1)
            self.assertEqual(sent, [])

    def test_send_without_secrets_does_not_raise(self):
        old = {k: os.environ.pop(k, None) for k in ("TELEGRAM_BOT_TOKEN", "OWNER_CHAT_ID")}
        try:
            self.assertFalse(owner_dm.send_owner_dm("hi"))
        finally:
            for k, v in old.items():
                if v is not None:
                    os.environ[k] = v

    def test_warning_text_is_in_the_dm_but_nothing_is_skipped(self):
        with tempfile.TemporaryDirectory() as root:
            ledger = []
            singles = []
            for i in range(60):  # $120 of singles already published this month
                pid = f"2026-10-{(i % 28) + 1:02d}_T{i}_vs_U{i}"
                singles.append((pid, f"2026-10-{(i % 28) + 1:02d}", f"T{i} vs U{i}", 1.5, True))
            make_repo(root, singles=singles, ledger=ledger)
            sent = []
            owner_dm.notify(self._meta_single(), root, {"telegram": {"ok": True}},
                            ["telegram"], send=sent.append, repo_root=root)
            self.assertEqual(len(sent), 1)  # still sent
            self.assertIn("WARNING: Staked", sent[0])


class SetMultiResultTests(unittest.TestCase):
    def test_writes_and_validates(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "multi_results.json")
            set_result("2026-10-01_weekend_multi", "Punter", "LOSS", path=path)
            with open(path) as f:
                self.assertEqual(json.load(f), {"2026-10-01_weekend_multi": {"punter": "loss"}})
            with self.assertRaises(ValueError):
                set_result("x", "nope", "win", path=path)
            with self.assertRaises(ValueError):
                set_result("x", "punter", "maybe", path=path)


if __name__ == "__main__":
    unittest.main()
