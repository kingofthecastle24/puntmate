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
