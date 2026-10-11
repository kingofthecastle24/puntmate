"""
Tests for build_review_package.py's Degen Watch wiring (2026-10-11,
Micah): on a genuine no-bet day, run_data["degen_watch"] (written by
main.py) gets frozen into the review package as its own text file +
card image, independently of the Watchlist, with intended_platforms
correctly reflecting Telegram (always) and Instagram (only when a card
was actually rendered).
"""
import os, sys, json, shutil, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_review_package as brp

DEGEN_CANDIDATE = {
    "cause": "not_backable",
    "match": "Warriors vs Storm",
    "sport_label": "NRL",
    "market_type": "h2h",
    "selection": "Storm to Win",
    "odds": 2.10,
    "reason": "edge too thin to back",
    "evidence_sufficient": True,
    "our_probability": 54.0,
    "implied_probability": 50.0,
    "edge_pct": 4.2,
    "min_value_edge_pct": 7.0,
}

WATCHLIST = [{"match": "Warriors vs Storm", "sport_label": "NRL", "kickoff": "2026-10-11T08:00:00Z"}]


class BuildReviewPackageDegenWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT)
        brp.REPO_ROOT = self.tmp
        brp.LATEST_RUN_PATH = os.path.join(self.tmp, "data", "latest_run.json")
        brp.CARDS_DIR = os.path.join(self.tmp, "data", "cards")
        brp.REVIEW_ROOT = os.path.join(self.tmp, "data", "review")
        os.makedirs(brp.CARDS_DIR, exist_ok=True)
        os.environ["GITHUB_REPOSITORY"] = "kingofthecastle24/puntmate"
        os.environ["GITHUB_RUN_ID"] = "12345"

    def tearDown(self):
        brp.REPO_ROOT, brp.LATEST_RUN_PATH, brp.CARDS_DIR, brp.REVIEW_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_run(self, degen_watch, with_card=True):
        os.makedirs(os.path.dirname(brp.LATEST_RUN_PATH), exist_ok=True)
        if with_card and degen_watch:
            card_path = os.path.join(self.tmp, "fake-card.png")
            with open(card_path, "wb") as f:
                f.write(b"FAKEPNG")
            degen_watch = {**degen_watch, "card_file": card_path}
        run_data = {
            "run_id": "12345", "run_date": "2026-10-11", "run_ts": "x", "status": "NO_VALUE",
            "pick": {"has_pick": False, "reasoning": "nothing today", "research_warnings": []},
            "watchlist": WATCHLIST,
        }
        if degen_watch is not None:
            run_data["degen_watch"] = degen_watch
        with open(brp.LATEST_RUN_PATH, "w") as f:
            json.dump(run_data, f)
        return run_data

    def test_degen_watch_with_card_gets_text_and_image_and_both_platforms(self):
        self._write_run({"candidate": DEGEN_CANDIDATE})
        brp.main()

        review_dirs = os.listdir(brp.REVIEW_ROOT)
        self.assertEqual(len(review_dirs), 1)
        review_dir = os.path.join(brp.REVIEW_ROOT, review_dirs[0])

        self.assertTrue(os.path.exists(os.path.join(review_dir, "degen-watch-post.txt")))
        self.assertTrue(os.path.exists(os.path.join(review_dir, "degen-watch.png")))

        metadata = json.load(open(os.path.join(review_dir, "post-metadata.json")))
        self.assertTrue(metadata["has_degen_watch"])
        self.assertIn("telegram", metadata["intended_platforms"])
        self.assertIn("instagram_feed", metadata["intended_platforms"])

        manifest = json.load(open(os.path.join(review_dir, "manifest.json")))
        self.assertIn("degen-watch-post.txt", manifest["files"])
        self.assertIn("degen-watch.png", manifest["files"])

    def test_degen_watch_without_a_card_is_telegram_only(self):
        self._write_run({"candidate": DEGEN_CANDIDATE}, with_card=False)
        brp.main()

        review_dir = os.path.join(brp.REVIEW_ROOT, os.listdir(brp.REVIEW_ROOT)[0])
        self.assertTrue(os.path.exists(os.path.join(review_dir, "degen-watch-post.txt")))
        self.assertFalse(os.path.exists(os.path.join(review_dir, "degen-watch.png")))

        metadata = json.load(open(os.path.join(review_dir, "post-metadata.json")))
        self.assertTrue(metadata["has_degen_watch"])
        self.assertIn("telegram", metadata["intended_platforms"])
        self.assertNotIn("instagram_feed", metadata["intended_platforms"])

    def test_no_degen_watch_key_means_no_degen_watch_files_at_all(self):
        self._write_run(None)
        brp.main()

        review_dir = os.path.join(brp.REVIEW_ROOT, os.listdir(brp.REVIEW_ROOT)[0])
        self.assertFalse(os.path.exists(os.path.join(review_dir, "degen-watch-post.txt")))
        metadata = json.load(open(os.path.join(review_dir, "post-metadata.json")))
        self.assertNotIn("has_degen_watch", metadata)

    def test_watchlist_still_builds_independently_of_degen_watch(self):
        self._write_run({"candidate": DEGEN_CANDIDATE})
        brp.main()

        review_dir = os.path.join(brp.REVIEW_ROOT, os.listdir(brp.REVIEW_ROOT)[0])
        self.assertTrue(os.path.exists(os.path.join(review_dir, "watchlist-post.txt")))
        metadata = json.load(open(os.path.join(review_dir, "post-metadata.json")))
        self.assertTrue(metadata["has_watchlist"])


if __name__ == "__main__":
    unittest.main()
