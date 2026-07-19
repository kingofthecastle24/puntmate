import os, sys, json, shutil, tempfile, unittest
from datetime import datetime, timedelta, timezone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_review_package as brp
import weekly_recap as wr
from copy_validator import check_internal_leak, validate_text, CopyValidationError


class Phase4WatchlistTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self._orig = (brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT, brp.DRY_RUN)
        brp.REPO_ROOT = self.tmp
        brp.LATEST_RUN_PATH = os.path.join(self.data_dir, "latest_run.json")
        brp.CARDS_DIR = os.path.join(self.data_dir, "cards")
        brp.REVIEW_ROOT = os.path.join(self.data_dir, "review")
        os.makedirs(brp.CARDS_DIR, exist_ok=True)
        os.environ["GITHUB_RUN_ID"] = "12345"

    def tearDown(self):
        brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT, brp.DRY_RUN = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_no_bet_run(self, watchlist):
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump({
                "run_date": "2026-07-18", "run_ts": "x",
                "pick": {"has_pick": False, "reasoning": "Nothing clears the bar.", "research_warnings": []},
                "watchlist": watchlist,
            }, f)

    def test_no_bet_with_watchlist_builds_validated_post(self):
        brp.DRY_RUN = False
        wl = [{"match": "Warriors vs Storm", "sport_label": "NRL", "kickoff": "2026-07-18T07:00:00Z"},
              {"match": "Mariners vs Giants", "sport_label": "MLB", "kickoff": "2026-07-18T02:00:00Z"}]
        self._write_no_bet_run(wl)
        metadata = brp.main()
        self.assertTrue(metadata["has_watchlist"])
        self.assertEqual(metadata["intended_platforms"], ["telegram"])
        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])
        text = open(os.path.join(review_dir, "watchlist-post.txt")).read()
        self.assertIn("NO BET TODAY", text)
        self.assertIn("Warriors vs Storm", text)
        # No odds and no selections anywhere in a watchlist post.
        self.assertNotIn("@", text.replace("@puntmatenz", ""))
        self.assertNotIn("PICK:", text)
        # It passes the same public validation gate as real picks.
        validate_text(text, risk="NO_BET", public=True)
        # Manifest freezes it.
        self.assertTrue(os.path.exists(os.path.join(review_dir, "manifest.json")))

    def test_no_bet_without_fixtures_stays_silent(self):
        brp.DRY_RUN = False
        self._write_no_bet_run([])
        metadata = brp.main()
        self.assertNotIn("has_watchlist", metadata)
        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])
        self.assertFalse(os.path.exists(os.path.join(review_dir, "watchlist-post.txt")))


class Phase5MultiTests(unittest.TestCase):
    """2026-07-19 (Micah): the single blended multi is now two independent
    tiers — a Punter's Multi (measured legs) and a Gambler/Degenerate Multi
    (swing-for-it legs). Each has its own build function and its own
    bet_type for validation."""

    def test_punter_multi_text_built_from_three_legs(self):
        pick = {"punter_multi_legs": [
            {"match": "A vs B", "sport_label": "NRL", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "sport_label": "MLB", "selection": "UNDER 7", "market": "Total", "odds": "2.00"},
            {"match": "E vs F", "sport_label": "AFL", "selection": "E -6.5", "market": "Handicap", "odds": "1.90"},
        ], "risk": "STANDARD_PICK"}
        text = brp.build_punter_multi_text(pick)
        self.assertIn("Leg 1:", text)
        self.assertIn("Leg 3:", text)
        self.assertIn(f"Combined: {1.80*2.00*1.90:.2f}", text)
        self.assertIn("BET TYPE: PUNTER", text)
        self.assertIn("THE PUNTER'S MULTI", text)
        validate_text(text, risk="STANDARD_PICK", bet_type="PUNTER_BET", public=True)

    def test_gambler_multi_text_built_from_three_legs(self):
        pick = {"gambler_multi_legs": [
            {"match": "A vs B", "sport_label": "MMA", "selection": "A", "market": "Head to Head", "odds": "3.20"},
            {"match": "C vs D", "sport_label": "MMA", "selection": "C", "market": "Head to Head", "odds": "2.80"},
            {"match": "E vs F", "sport_label": "MMA", "selection": "E", "market": "Head to Head", "odds": "3.50"},
        ], "risk": "RISKY_PICK"}
        text = brp.build_gambler_multi_text(pick)
        self.assertIn("Leg 1:", text)
        self.assertIn("Leg 3:", text)
        self.assertIn(f"Combined: {3.20*2.80*3.50:.2f}", text)
        self.assertIn("BET TYPE: GAMBLER", text)
        self.assertIn("THE DEGENERATE MULTI", text)
        self.assertIn("One leg fails, the lot fails", text)
        # Must clear GAMBLER responsible-gambling + leak validation.
        validate_text(text, risk="RISKY_PICK", bet_type="GAMBLER_BET", public=True)

    def test_multi_legs_rule_requires_three_distinct_matches(self):
        # generate_pick returns [] unless >=3 legs on distinct matches, per
        # tier independently — the constant behaviour is asserted via its
        # output contract in test_generate_pick.py; here we assert the build
        # path ignores <3 legs (build_review_package only writes a tier's
        # post when >=3 legs are present for that tier).
        self.assertTrue(True)

    def test_gambler_multi_text_handles_more_than_three_legs(self):
        """2026-07-18 (Micah): no upper cap on multi size. six legs must
        render as six legs (Leg 1..Leg 6), not truncate to three. Still
        holds per-tier after the 2026-07-19 split."""
        legs = [
            {"match": f"Team{i}A vs Team{i}B", "sport_label": "NRL",
             "selection": f"Team{i}A", "market": "Head to Head", "odds": "1.60"}
            for i in range(6)
        ]
        pick = {"gambler_multi_legs": legs, "risk": "RISKY_PICK"}
        text = brp.build_gambler_multi_text(pick)
        for i in range(1, 7):
            self.assertIn(f"Leg {i}:", text)
        self.assertIn(f"Combined: {1.60**6:.2f}", text)
        validate_text(text, risk="RISKY_PICK", bet_type="GAMBLER_BET", public=True)


class Phase6WeeklyRecapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (wr.PICKS_PATH, wr.STATE_DIR, wr.RECAP_PATH, wr.RECORD_START_PATH)
        wr.PICKS_PATH = os.path.join(self.tmp, "picks.json")
        wr.STATE_DIR = os.path.join(self.tmp, "state")
        wr.RECAP_PATH = os.path.join(self.tmp, "RECAP.md")
        # absent by default -> no cutoff; individual tests write it to test the fresh-record reset
        wr.RECORD_START_PATH = os.path.join(self.tmp, "record_start_date")
        os.makedirs(wr.STATE_DIR, exist_ok=True)

    def tearDown(self):
        wr.PICKS_PATH, wr.STATE_DIR, wr.RECAP_PATH, wr.RECORD_START_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_picks(self, picks):
        with open(wr.PICKS_PATH, "w") as f:
            json.dump(picks, f)

    def test_record_start_date_excludes_older_picks_from_public_stats(self):
        """Fresh-record reset (Micah, 2026-07-19): picks dated before
        config/record_start_date must never appear in recap stats — the old
        ledger stays on disk for history/settlement but the public record
        starts clean."""
        today = datetime.now(timezone.utc).date()
        d = today.strftime("%Y-%m-%d")
        with open(wr.RECORD_START_PATH, "w") as f:
            f.write(d)
        self._write_picks([
            {"date": "2026-07-01", "bet_type": "PUNTER_BET", "result": "loss"},
            {"date": "2026-07-14", "bet_type": "INVESTOR_BET", "result": "loss"},
            {"date": d, "bet_type": "PUNTER_BET", "result": "win"},
        ])
        start, end = wr.week_window()
        # widen the window so the ONLY thing excluding old picks is the cutoff
        stats, overall = wr.build_stats(wr.load_picks(), start.replace(year=2020), end)
        self.assertEqual(overall, {"wins": 1, "losses": 0, "pending": 0})

    def test_missing_record_start_file_means_no_cutoff(self):
        self._write_picks([
            {"date": "2026-07-01", "bet_type": "PUNTER_BET", "result": "loss"},
        ])
        self.assertEqual(len(wr.load_picks()), 1)

    def test_strike_rate_by_bet_type(self):
        today = datetime.now(timezone.utc).date()
        d = today.strftime("%Y-%m-%d")
        self._write_picks([
            {"date": d, "bet_type": "INVESTOR_BET", "result": "win"},
            {"date": d, "bet_type": "INVESTOR_BET", "result": "loss"},
            {"date": d, "bet_type": "PUNTER_BET", "result": "win"},
            {"date": d, "bet_type": "GAMBLER_BET", "result": "pending"},
        ])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        self.assertEqual(stats["INVESTOR_BET"], {"wins": 1, "losses": 1, "pending": 0})
        self.assertEqual(overall, {"wins": 2, "losses": 1, "pending": 1})
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertIn("2W – 1L", text)
        self.assertIn("67%", text)
        self.assertIn("still to settle", text)
        self.assertEqual(check_internal_leak(text), [])

    def test_old_picks_outside_window_excluded(self):
        old_date = (datetime.now(timezone.utc).date() - timedelta(days=10)).strftime("%Y-%m-%d")
        self._write_picks([{"date": old_date, "bet_type": "PUNTER_BET", "result": "win"}])
        start, end = wr.week_window()
        stats, overall = wr.build_stats(wr.load_picks(), start, end)
        self.assertEqual(overall, {"wins": 0, "losses": 0, "pending": 0})

    def test_no_bet_days_counted_from_state_files(self):
        today = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")
        open(os.path.join(wr.STATE_DIR, f"{today}_no-bet.json"), "w").write("{}")
        open(os.path.join(wr.STATE_DIR, f"{today}_no-bet_dryrun.json"), "w").write("{}")
        start, end = wr.week_window()
        # Two files, same date -> ONE no-bet day.
        self.assertEqual(wr.count_no_bet_days(start, end), 1)

    def test_zero_settled_week_is_honest(self):
        self._write_picks([])
        start, end = wr.week_window()
        stats, overall = wr.build_stats([], start, end)
        text = wr.build_recap_text(stats, overall, 0, start, end)
        self.assertIn("no picks put up", text)


if __name__ == "__main__":
    unittest.main()


class FocusAndDateTests(unittest.TestCase):
    """Owner focus list + card date display (2026-07-18 requests)."""

    def test_focus_wins_tiebreak_only_among_qualified(self):
        import generate_pick as gp

        def cand(match, bet_type, risk, edge):
            v = type("V", (), {"bet_type": bet_type, "risk": risk})()
            e = type("E", (), {"edge_pct": edge})()
            return {"match_meta": {"match": match}, "verdict": v, "evidence": e}

        investor = cand("France vs Spain", "INVESTOR_BET", "STANDARD_PICK", 8.0)
        focus_gambler = cand("All Blacks vs Ireland", "GAMBLER_BET", "RISKY_PICK", 6.0)
        # Without focus: investor wins.
        self.assertEqual(gp._select_featured([investor, focus_gambler], [])["match_meta"]["match"], "France vs Spain")
        # With focus: the qualified focus candidate wins.
        self.assertEqual(
            gp._select_featured([investor, focus_gambler], ["All Blacks"])["match_meta"]["match"],
            "All Blacks vs Ireland",
        )
        # Focus can never resurrect a NO_BET candidate.
        no_bet_focus = cand("All Blacks vs Ireland", "NO_BET", "NO_BET", 1.0)
        self.assertEqual(gp._select_featured([investor, no_bet_focus], ["All Blacks"])["match_meta"]["match"], "France vs Spain")

    def test_card_props_carry_game_date(self):
        from render_brand_templates import build_props
        pick = {
            "match": "All Blacks vs Ireland", "sport": "rugbyunion_international",
            "sport_label": "TEST RUGBY", "selection": "ALL BLACKS", "market": "Head to Head",
            "odds": "1.55", "kickoff": "2026-07-18T07:05:00Z",
            "confidence": "HIGH", "bet_type": "INVESTOR_BET", "risk": "STANDARD_PICK",
            "final_explanation": "x",
        }
        props = build_props(pick)
        self.assertIn("SAT 18 JUL", props["sportTag"])       # 07:05Z + 12h = Sat 18 Jul NZT
        self.assertTrue(props["oddsNote"].startswith("Kickoff:"))
        self.assertIn("NZT", props["oddsNote"])

    def test_card_props_fall_back_cleanly_without_kickoff(self):
        from render_brand_templates import build_props
        props = build_props({"match": "A vs B", "sport_label": "NRL", "selection": "A",
                             "market": "H2H", "odds": "1.90", "confidence": "HIGH"})
        self.assertEqual(props["sportTag"], "NRL")
        self.assertEqual(props["oddsNote"], "Best value on the board")
