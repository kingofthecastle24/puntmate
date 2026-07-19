import os, sys, json, shutil, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_review_package as brp
import workflow_state as ws


def _standard_pick():
    return {
        "has_pick": True,
        "match": "Warriors vs Storm",
        "sport": "rugbyleague_nrl",
        "sport_label": "NRL",
        "home_team": "Warriors",
        "away_team": "Storm",
        "kickoff": "2026-07-15T08:00:00Z",
        "selection": "WARRIORS",
        "market": "Head to Head",
        "odds": "1.90",
        "our_probability": 60,
        "implied_probability": 50,
        "edge_pct": 10,
        "risk": "STANDARD_PICK",
        "bet_type": "INVESTOR_BET",
        "bet_type_label": "BET TYPE: INVESTOR",
        "bet_type_reason": "This one's about as close to a sure thing as sport gets — the numbers stack up and the price still pays. Warriors have won four straight at home.",
        "final_explanation": "Warriors have won four straight at home and Storm are missing two starters.",
        "confidence": "HIGH",
        "confidence_label": "HIGH",
        "uncertainty_flags": [],
        "public_caution": None,
        "research_warnings": [],
        "big_game": False,
    }


class BuildReviewPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo_root = self.tmp
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self._orig = (brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT)
        brp.REPO_ROOT = self.repo_root
        brp.LATEST_RUN_PATH = os.path.join(self.data_dir, "latest_run.json")
        brp.CARDS_DIR = os.path.join(self.data_dir, "cards")
        brp.REVIEW_ROOT = os.path.join(self.data_dir, "review")
        os.makedirs(brp.CARDS_DIR, exist_ok=True)
        os.environ["GITHUB_REPOSITORY"] = "kingofthecastle24/puntmate"
        os.environ["GITHUB_RUN_ID"] = "12345"

    def tearDown(self):
        brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_run(self, pick):
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump({"run_date": "2026-07-15", "run_ts": "x", "pick": pick}, f)

    def _write_fake_cards(self, base):
        for suffix in ("_1_cover.png", "_2_tip.png", "_3_breakdown.png", "_story.png"):
            with open(os.path.join(brp.CARDS_DIR, base + suffix), "wb") as f:
                f.write(b"FAKEPNGDATA")

    def test_full_package_has_exact_required_filenames(self):
        pick = _standard_pick()
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)

        metadata = brp.main()
        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])
        required = {"telegram-post.txt", "instagram-caption.txt", "post-metadata.json", "preview.html", "manifest.json"}
        actual = set(os.listdir(review_dir))
        self.assertTrue(required.issubset(actual), f"missing: {required - actual}")
        # Must NOT create a personality-perspectives.json artifact
        self.assertNotIn("personality-perspectives.json", actual)

    def test_manifest_checksums_verify_against_written_files(self):
        pick = _standard_pick()
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)
        metadata = brp.main()
        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])

        from manifest import load_manifest, verify_manifest
        manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
        ok, mismatches = verify_manifest(manifest, review_dir)
        self.assertTrue(ok, mismatches)

    def test_post_metadata_excludes_staking_and_personality_fields(self):
        pick = _standard_pick()
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)
        metadata = brp.main()
        for banned_key in ("suggested_stake", "stake", "stake_amount", "personality", "personality_summaries"):
            self.assertNotIn(banned_key, metadata)

    def test_stale_multi_files_from_previous_run_are_deleted_when_tier_does_not_fire(self):
        """REGRESSION (real dry run #56, 2026-07-19): re-running a pick_id
        whose review dir already contained multi files from an earlier run
        (committed to main by pre-weekend-multi code) left those files in
        place, and publish_pick re-posted them. When a tier doesn't fire,
        freezing must remove that tier's leftovers and stamp the metadata
        flag False."""
        pick = _standard_pick()  # no multi legs at all
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)

        # Pre-seed the review dir with stale tier files, as run #56 found them
        review_dir = os.path.join(brp.REVIEW_ROOT, f"2026-07-15_{slug}{brp._pick_id_suffix()}")
        os.makedirs(review_dir, exist_ok=True)
        stale_names = ["punter-multi-post.txt", "punter_multi_cover.png",
                       "punter_multi_legs.png", "punter_multi_breakdown.png"]
        for name in stale_names:
            with open(os.path.join(review_dir, name), "w") as f:
                f.write("STALE")

        metadata = brp.main()
        actual = set(os.listdir(os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])))
        for name in stale_names:
            self.assertNotIn(name, actual)
        self.assertIs(metadata.get("has_punter_multi"), False)
        self.assertIs(metadata.get("has_gambler_multi"), False)

    def test_multi_flags_actually_reach_frozen_metadata_and_preview(self):
        """Regression test (2026-07-18, updated 2026-07-19 for the two-tier
        split): has_multi/multi_promo_hint used to be set on the metadata
        dict AFTER post-metadata.json and preview.html were already written
        to disk, so neither file -- nor therefore the Gmail preview or job
        summary built from them -- ever showed that a multi existed at all.
        build_review_package.main() now computes both multi tiers first."""
        pick = _standard_pick()
        pick["punter_multi_legs"] = [
            {"match": "A vs B", "sport_label": "MLB", "selection": "A", "market": "Head to Head", "odds": "1.80"},
            {"match": "C vs D", "sport_label": "MLB", "selection": "C", "market": "Head to Head", "odds": "1.90"},
            {"match": "E vs F", "sport_label": "MLB", "selection": "E", "market": "Head to Head", "odds": "1.70"},
        ]
        pick["punter_multi_promo_hint"] = "All 3 legs fall within TAB's 'us team sports' category — test hint."
        pick["gambler_multi_legs"] = []
        pick["gambler_multi_promo_hint"] = None
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)

        metadata = brp.main()
        self.assertTrue(metadata.get("has_punter_multi"))
        # Explicit False (not merely absent) as of the stale-file fix —
        # publish_pick keys off this flag, so it must always be present.
        self.assertIs(metadata.get("has_gambler_multi"), False)
        self.assertEqual(metadata.get("punter_multi_promo_hint"), pick["punter_multi_promo_hint"])

        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])
        with open(os.path.join(review_dir, "post-metadata.json")) as f:
            on_disk = json.load(f)
        self.assertTrue(on_disk.get("has_punter_multi"))
        self.assertEqual(on_disk.get("punter_multi_promo_hint"), pick["punter_multi_promo_hint"])
        # And never in the public multi text itself.
        with open(os.path.join(review_dir, "punter-multi-post.txt")) as f:
            multi_text = f.read()
        self.assertNotIn("us team sports", multi_text)
        self.assertFalse(os.path.exists(os.path.join(review_dir, "gambler-multi-post.txt")))

    def test_both_multi_tiers_can_fire_independently_same_day(self):
        """A day can produce a Punter Multi AND a Gambler Multi
        at the same time — they're independent, not mutually exclusive."""
        pick = _standard_pick()
        pick["punter_multi_legs"] = [
            {"match": "A vs B", "sport_label": "NRL", "selection": "A", "market": "Head to Head", "odds": "1.60"},
            {"match": "C vs D", "sport_label": "NRL", "selection": "C", "market": "Head to Head", "odds": "1.55"},
            {"match": "E vs F", "sport_label": "NRL", "selection": "E", "market": "Head to Head", "odds": "1.70"},
        ]
        pick["gambler_multi_legs"] = [
            {"match": "G vs H", "sport_label": "MMA", "selection": "G", "market": "Head to Head", "odds": "3.20"},
            {"match": "I vs J", "sport_label": "MMA", "selection": "I", "market": "Head to Head", "odds": "2.80"},
            {"match": "K vs L", "sport_label": "MMA", "selection": "K", "market": "Head to Head", "odds": "3.50"},
        ]
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        base = f"2026-07-15_{slug}_{theme}"
        self._write_fake_cards(base)

        metadata = brp.main()
        self.assertTrue(metadata.get("has_punter_multi"))
        self.assertTrue(metadata.get("has_gambler_multi"))
        review_dir = os.path.join(brp.REVIEW_ROOT, metadata["pick_id"])
        self.assertTrue(os.path.exists(os.path.join(review_dir, "punter-multi-post.txt")))
        self.assertTrue(os.path.exists(os.path.join(review_dir, "gambler-multi-post.txt")))
        with open(os.path.join(review_dir, "gambler-multi-post.txt")) as f:
            gambler_text = f.read()
        self.assertIn("THE GAMBLER MULTI", gambler_text)
        self.assertIn("BET TYPE: GAMBLER", gambler_text)

    def test_no_bet_writes_metadata_only_no_images_no_approval_fields(self):
        no_bet_pick = {"has_pick": False, "reasoning": "Nothing clears the bar today.", "research_warnings": []}
        self._write_run(no_bet_pick)
        metadata = brp.main()
        self.assertFalse(metadata["has_pick"])
        self.assertEqual(metadata["intended_platforms"], [])
        self.assertNotIn("selection", metadata)
        self.assertNotIn("odds", metadata)


class DryRunPickIdNamespaceTests(unittest.TestCase):
    """Covers the fix for the real collision Micah hit: a dry-run test run
    parked a match's pick_id at AWAITING_APPROVAL for the rest of the day,
    so any subsequent real run on the same fixture crashed with
    workflow_state.InvalidTransitionError (AWAITING_APPROVAL -> GENERATED).
    Dry-run pick_ids now get a "_dryrun" suffix so they can never collide
    with — or terminally block — a same-day live run on the same match."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.repo_root = self.tmp
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self._orig = (brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT, brp.DRY_RUN)
        brp.REPO_ROOT = self.repo_root
        brp.LATEST_RUN_PATH = os.path.join(self.data_dir, "latest_run.json")
        brp.CARDS_DIR = os.path.join(self.data_dir, "cards")
        brp.REVIEW_ROOT = os.path.join(self.data_dir, "review")
        os.makedirs(brp.CARDS_DIR, exist_ok=True)
        os.environ["GITHUB_REPOSITORY"] = "kingofthecastle24/puntmate"
        os.environ["GITHUB_RUN_ID"] = "12345"

    def tearDown(self):
        brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT, brp.DRY_RUN = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_run(self, pick, run_date="2026-07-17"):
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump({"run_date": run_date, "run_ts": "x", "pick": pick}, f)

    def _write_fake_cards(self, base):
        for suffix in ("_1_cover.png", "_2_tip.png", "_3_breakdown.png", "_story.png"):
            with open(os.path.join(brp.CARDS_DIR, base + suffix), "wb") as f:
                f.write(b"FAKEPNGDATA")

    def test_dry_run_pick_id_gets_dryrun_suffix(self):
        brp.DRY_RUN = True
        pick = _standard_pick()
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        self._write_fake_cards(f"2026-07-17_{slug}_{theme}")

        metadata = brp.main()
        self.assertEqual(metadata["pick_id"], f"2026-07-17_{slug}_dryrun")

    def test_live_run_pick_id_has_no_suffix(self):
        brp.DRY_RUN = False
        pick = _standard_pick()
        self._write_run(pick)
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        self._write_fake_cards(f"2026-07-17_{slug}_{theme}")

        metadata = brp.main()
        self.assertEqual(metadata["pick_id"], f"2026-07-17_{slug}")
        self.assertFalse(metadata["pick_id"].endswith("_dryrun"))

    def test_no_bet_dry_run_pick_id_gets_suffix(self):
        brp.DRY_RUN = True
        no_bet_pick = {"has_pick": False, "reasoning": "Nothing clears the bar today.", "research_warnings": []}
        self._write_run(no_bet_pick)
        metadata = brp.main()
        self.assertEqual(metadata["pick_id"], "2026-07-17_no-bet_dryrun")

    def test_no_bet_live_pick_id_has_no_suffix(self):
        brp.DRY_RUN = False
        no_bet_pick = {"has_pick": False, "reasoning": "Nothing clears the bar today.", "research_warnings": []}
        self._write_run(no_bet_pick)
        metadata = brp.main()
        self.assertEqual(metadata["pick_id"], "2026-07-17_no-bet")

    def test_dry_run_and_live_pick_ids_differ_for_same_match_same_day(self):
        pick = _standard_pick()
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        self._write_fake_cards(f"2026-07-17_{slug}_{theme}")

        brp.DRY_RUN = True
        self._write_run(pick)
        dry_metadata = brp.main()

        brp.DRY_RUN = False
        self._write_run(pick)
        live_metadata = brp.main()

        self.assertNotEqual(dry_metadata["pick_id"], live_metadata["pick_id"])
        # And each gets its own isolated review package directory.
        self.assertNotEqual(
            os.path.join(brp.REVIEW_ROOT, dry_metadata["pick_id"]),
            os.path.join(brp.REVIEW_ROOT, live_metadata["pick_id"]),
        )

    def test_reproduces_and_resolves_the_real_collision_scenario(self):
        """Mirrors exactly what happened in production: a dry-run test run on
        a real fixture reaches AWAITING_APPROVAL (unresolved, sitting at the
        approval gate) and is left alone (never approved or rejected — same
        as the live incident). A fresh run is then triggered on the identical
        match, same day, with dry_run=false. Before the fix this crashed with
        InvalidTransitionError: AWAITING_APPROVAL -> GENERATED because both
        runs computed the same pick_id. After the fix the two runs get
        different pick_ids, so the live run's GENERATED transition succeeds
        cleanly even though the dry-run pick is still stuck unresolved."""
        pick = _standard_pick()
        theme = brp.choose_theme(pick)
        slug = brp.slugify(pick["match"])
        self._write_fake_cards(f"2026-07-17_{slug}_{theme}")

        # 1. Earlier dry-run test run — reaches AWAITING_APPROVAL and is
        #    left unresolved, exactly like the real incident.
        brp.DRY_RUN = True
        self._write_run(pick)
        dry_metadata = brp.main()
        dry_pick_id = dry_metadata["pick_id"]
        ws.transition(self.repo_root, dry_pick_id, ws.GENERATED, note="review package built")
        ws.transition(self.repo_root, dry_pick_id, ws.PREVIEW_READY, note="review package frozen")
        ws.transition(self.repo_root, dry_pick_id, ws.AWAITING_APPROVAL, note="entering GitHub environment approval gate")
        self.assertEqual(ws.load_state(self.repo_root, dry_pick_id)["state"], ws.AWAITING_APPROVAL)

        # 2. Fresh live run triggered later the same day, same fixture.
        brp.DRY_RUN = False
        self._write_run(pick)
        live_metadata = brp.main()
        live_pick_id = live_metadata["pick_id"]

        # This is the exact call that crashed before the fix (send_preview.py's
        # first transition on a fresh run). Must succeed now.
        ws.transition(self.repo_root, live_pick_id, ws.GENERATED, note="review package built")
        ws.transition(self.repo_root, live_pick_id, ws.PREVIEW_READY, note="review package frozen")
        ws.transition(self.repo_root, live_pick_id, ws.AWAITING_APPROVAL, note="entering GitHub environment approval gate")
        self.assertEqual(ws.load_state(self.repo_root, live_pick_id)["state"], ws.AWAITING_APPROVAL)

        # The dry-run pick's state is untouched by the live run — proves
        # isolation, not just "didn't crash".
        self.assertEqual(ws.load_state(self.repo_root, dry_pick_id)["state"], ws.AWAITING_APPROVAL)
        self.assertNotEqual(dry_pick_id, live_pick_id)


if __name__ == "__main__":
    unittest.main()
