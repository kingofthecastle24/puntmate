import os, sys, json, shutil, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_weekend_multi_package as bwmp
import build_review_package as brp


def _run_data(punter_n=3, gambler_n=0, gambler_hint=None):
    return {
        "run_date": "2026-07-24",
        "punter_multi_legs": [
            {"match": f"Team{i}A vs Team{i}B", "sport_label": "NRL", "selection": f"Team{i}A", "market": "Head to Head", "odds": "1.70"}
            for i in range(punter_n)
        ],
        "punter_multi_promo_hint": None,
        "gambler_multi_legs": [
            {"match": f"Fighter{i}A vs Fighter{i}B", "sport_label": "UFC", "selection": f"Fighter{i}A", "market": "Head to Head", "odds": "3.20"}
            for i in range(gambler_n)
        ],
        "gambler_multi_promo_hint": gambler_hint,
        "research_warnings": [],
        "anchor_pick": {"match": "Weekend Multi", "home_team": "Weekend", "away_team": "Multi"},
    }


class BuildWeekendMultiPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ["GITHUB_REPOSITORY"] = "kingofthecastle24/puntmate"
        self._orig = (bwmp.REPO_ROOT, bwmp.LATEST_WEEKEND_RUN_PATH, bwmp.CARDS_DIR, bwmp.REVIEW_ROOT, brp.DRY_RUN)
        bwmp.REPO_ROOT = self.tmp
        bwmp.LATEST_WEEKEND_RUN_PATH = os.path.join(self.tmp, "data", "latest_weekend_run.json")
        bwmp.CARDS_DIR = os.path.join(self.tmp, "data", "cards")
        bwmp.REVIEW_ROOT = os.path.join(self.tmp, "data", "review")
        brp.DRY_RUN = False
        os.makedirs(bwmp.CARDS_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(bwmp.LATEST_WEEKEND_RUN_PATH), exist_ok=True)

    def tearDown(self):
        bwmp.REPO_ROOT, bwmp.LATEST_WEEKEND_RUN_PATH, bwmp.CARDS_DIR, bwmp.REVIEW_ROOT, brp.DRY_RUN = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_run(self, run_data):
        with open(bwmp.LATEST_WEEKEND_RUN_PATH, "w") as f:
            json.dump(run_data, f)

    def _fake_graphic(self, tier, run_date="2026-07-24"):
        anchor = {"match": "Weekend Multi"}
        theme = brp.choose_theme(anchor)
        slug = brp.slugify(anchor["match"])
        base = f"{run_date}_{slug}_{theme}"
        for n in ("1_cover", "2_legs", "3_breakdown"):
            with open(os.path.join(bwmp.CARDS_DIR, f"{base}_{tier}_multi_{n}.png"), "wb") as f:
                f.write(b"FAKE")

    def test_pick_id_uses_weekend_multi_suffix(self):
        self._write_run(_run_data())
        metadata = bwmp.main()
        self.assertEqual(metadata["pick_id"], "2026-07-24_weekend_multi")
        self.assertTrue(metadata["is_weekend_multi"])
        self.assertFalse(metadata["has_pick"])

    def test_both_tiers_frozen_when_both_clear_the_bar(self):
        self._write_run(_run_data(punter_n=3, gambler_n=3, gambler_hint="test hint"))
        self._fake_graphic("punter")
        self._fake_graphic("gambler")
        metadata = bwmp.main()

        self.assertTrue(metadata["has_punter_multi"])
        self.assertTrue(metadata["has_gambler_multi"])
        self.assertEqual(metadata["gambler_multi_promo_hint"], "test hint")
        review_dir = os.path.join(bwmp.REVIEW_ROOT, metadata["pick_id"])
        self.assertTrue(os.path.exists(os.path.join(review_dir, "punter-multi-post.txt")))
        self.assertTrue(os.path.exists(os.path.join(review_dir, "gambler-multi-post.txt")))
        self.assertTrue(os.path.exists(os.path.join(review_dir, "punter_multi_cover.png")))
        self.assertTrue(os.path.exists(os.path.join(review_dir, "gambler_multi_cover.png")))
        self.assertEqual(set(metadata["intended_platforms"]), {"telegram", "instagram_feed"})

    def test_only_qualifying_tier_gets_files(self):
        self._write_run(_run_data(punter_n=3, gambler_n=2))  # gambler below the 3-leg floor
        self._fake_graphic("punter")
        metadata = bwmp.main()

        self.assertTrue(metadata["has_punter_multi"])
        # Explicit False (not absent) since the stale-file fix — publish
        # keys off this flag.
        self.assertIs(metadata.get("has_gambler_multi"), False)
        review_dir = os.path.join(bwmp.REVIEW_ROOT, metadata["pick_id"])
        self.assertFalse(os.path.exists(os.path.join(review_dir, "gambler-multi-post.txt")))

    def test_neither_tier_clearing_writes_metadata_only(self):
        self._write_run(_run_data(punter_n=1, gambler_n=0))
        metadata = bwmp.main()

        self.assertIs(metadata.get("has_punter_multi"), False)
        self.assertIs(metadata.get("has_gambler_multi"), False)
        review_dir = os.path.join(bwmp.REVIEW_ROOT, metadata["pick_id"])
        self.assertEqual(sorted(os.listdir(review_dir)), ["manifest.json", "post-metadata.json"])

    def test_manifest_checksums_verify(self):
        self._write_run(_run_data(punter_n=3))
        self._fake_graphic("punter")
        metadata = bwmp.main()
        review_dir = os.path.join(bwmp.REVIEW_ROOT, metadata["pick_id"])

        from manifest import load_manifest, verify_manifest
        manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
        ok, mismatches = verify_manifest(manifest, review_dir)
        self.assertTrue(ok, mismatches)

    def test_gambler_multi_text_is_clean_of_leaked_promo_hint(self):
        self._write_run(_run_data(punter_n=0, gambler_n=3, gambler_hint="all 3 legs fall within TAB's mma category"))
        self._fake_graphic("gambler")
        metadata = bwmp.main()
        review_dir = os.path.join(bwmp.REVIEW_ROOT, metadata["pick_id"])
        with open(os.path.join(review_dir, "gambler-multi-post.txt")) as f:
            text = f.read()
        self.assertNotIn("TAB's mma category", text)
        self.assertEqual(metadata["gambler_multi_promo_hint"], "all 3 legs fall within TAB's mma category")


if __name__ == "__main__":
    unittest.main()
