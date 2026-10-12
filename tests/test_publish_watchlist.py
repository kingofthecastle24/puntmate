"""
Tests for publish_watchlist.py, which publishes both the No-Bet Watchlist
(Telegram text only, pre-existing) and, when present, Degen Watch
(2026-10-11, Micah) -- the candidate closest to clearing today's value
bar, explicitly unofficial, to Telegram (text) and Instagram (card).
No existing test file covered this script before; these also exercise
the pre-existing watchlist-only path so a future regression there is
caught too.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import publish_watchlist as pw
from manifest import build_manifest, write_manifest
from workflow_state import transition, load_state, GENERATED, PREVIEW_READY, AWAITING_APPROVAL, \
    PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED


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


def _write_manifest(review_dir, pick_id, manifest_files):
    manifest = build_manifest(review_dir, manifest_files, extra={"pick_id": pick_id})
    write_manifest(manifest, os.path.join(review_dir, "manifest.json"))


def _make_watchlist_only_package(review_dir, pick_id):
    os.makedirs(review_dir, exist_ok=True)
    with open(os.path.join(review_dir, "watchlist-post.txt"), "w") as f:
        f.write("On the watchlist today: NRL Warriors vs Storm")
    metadata = {"pick_id": pick_id, "has_watchlist": True, "has_degen_watch": False}
    with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
        json.dump(metadata, f)
    _write_manifest(review_dir, pick_id, ["watchlist-post.txt", "post-metadata.json"])
    return metadata


def _make_degen_watch_package(review_dir, pick_id, with_card=True, with_watchlist=True):
    os.makedirs(review_dir, exist_ok=True)
    manifest_files = ["post-metadata.json"]
    metadata = {"pick_id": pick_id, "has_watchlist": with_watchlist, "has_degen_watch": True, "degen_watch": DEGEN_CANDIDATE}
    if with_watchlist:
        with open(os.path.join(review_dir, "watchlist-post.txt"), "w") as f:
            f.write("On the watchlist today: NRL Warriors vs Storm")
        manifest_files.append("watchlist-post.txt")
    with open(os.path.join(review_dir, "degen-watch-post.txt"), "w") as f:
        f.write("DEGEN WATCH — Storm to Win @ 2.10, unofficial.")
    manifest_files.append("degen-watch-post.txt")
    if with_card:
        with open(os.path.join(review_dir, "degen-watch.png"), "wb") as f:
            f.write(b"FAKEPNG")
        manifest_files.append("degen-watch.png")
    with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
        json.dump(metadata, f)
    _write_manifest(review_dir, pick_id, manifest_files)
    return metadata


class PublishWatchlistTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", "test-channel")
        self.tmp = tempfile.mkdtemp()
        self._orig = (pw.REPO_ROOT, pw.REVIEW_ROOT, pw.PUBLISHED_DIR, pw.DRY_RUN)
        pw.REPO_ROOT = self.tmp
        pw.REVIEW_ROOT = os.path.join(self.tmp, "review")
        pw.PUBLISHED_DIR = os.path.join(self.tmp, "published")

    def tearDown(self):
        pw.REPO_ROOT, pw.REVIEW_ROOT, pw.PUBLISHED_DIR, pw.DRY_RUN = self._orig
        os.environ.pop("PICK_ID", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_through_approval(self, pick_id):
        transition(pw.REPO_ROOT, pick_id, GENERATED)
        transition(pw.REPO_ROOT, pick_id, PREVIEW_READY)
        transition(pw.REPO_ROOT, pick_id, AWAITING_APPROVAL)

    # ---- pre-existing watchlist-only path (no prior dedicated test file) ----

    @patch("post_telegram.post_text")
    def test_watchlist_only_publishes_and_marks_published(self, mock_post):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_watchlist_only_package(review_dir, pick_id)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        mock_post.return_value = {"ok": True}

        pw.main()

        self.assertEqual(load_state(pw.REPO_ROOT, pick_id)["state"], PUBLISHED)
        mock_post.assert_called_once()

    def test_watchlist_only_dry_run_never_calls_telegram(self):
        pw.DRY_RUN = True
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_watchlist_only_package(review_dir, pick_id)
        os.environ["PICK_ID"] = pick_id

        with patch("post_telegram.post_text") as mock_post:
            pw.main()
            mock_post.assert_not_called()

    # ---- Degen Watch ----

    @patch("post_instagram.post_degen_watch_to_instagram")
    @patch("post_telegram.post_text")
    def test_degen_watch_with_card_posts_to_both_platforms(self, mock_tg, mock_ig):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_degen_watch_package(review_dir, pick_id, with_card=True)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        mock_tg.return_value = {"ok": True}
        mock_ig.return_value = True

        pw.main()

        self.assertEqual(mock_tg.call_count, 2)  # watchlist + degen watch text
        mock_ig.assert_called_once()
        self.assertEqual(load_state(pw.REPO_ROOT, pick_id)["state"], PUBLISHED)
        published = json.load(open(os.path.join(pw.PUBLISHED_DIR, pick_id + ".json")))
        self.assertTrue(published["telegram_degen_watch"]["ok"])
        self.assertTrue(published["instagram_degen_watch"]["ok"])

    @patch("post_instagram.post_degen_watch_to_instagram")
    @patch("post_telegram.post_text")
    def test_degen_watch_without_a_rendered_card_is_telegram_only_and_still_published(self, mock_tg, mock_ig):
        # Card render failed upstream (main.py's render_degen_watch_card
        # returns None on failure) -- Telegram-only must still succeed,
        # Instagram must be skipped (not failed), and the day's result is
        # still PUBLISHED, not partial.
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_degen_watch_package(review_dir, pick_id, with_card=False)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        mock_tg.return_value = {"ok": True}

        pw.main()

        mock_ig.assert_not_called()
        self.assertEqual(load_state(pw.REPO_ROOT, pick_id)["state"], PUBLISHED)
        published = json.load(open(os.path.join(pw.PUBLISHED_DIR, pick_id + ".json")))
        self.assertTrue(published["instagram_degen_watch"]["skipped"])

    @patch("post_instagram.post_degen_watch_to_instagram")
    @patch("post_telegram.post_text")
    def test_instagram_failure_is_partial_publish_not_rollback(self, mock_tg, mock_ig):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_degen_watch_package(review_dir, pick_id, with_card=True)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        mock_tg.return_value = {"ok": True}
        mock_ig.return_value = False  # Instagram post failed

        pw.main()

        self.assertEqual(load_state(pw.REPO_ROOT, pick_id)["state"], PARTIALLY_PUBLISHED)
        # Telegram (both watchlist and degen watch) still went out.
        self.assertEqual(mock_tg.call_count, 2)

    @patch("post_telegram.post_text")
    def test_watchlist_and_degen_watch_text_are_independent_telegram_posts(self, mock_tg):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_degen_watch_package(review_dir, pick_id, with_card=False, with_watchlist=True)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        mock_tg.return_value = {"ok": True}

        pw.main()

        sent_texts = [c.args[0] for c in mock_tg.call_args_list]
        self.assertTrue(any("watchlist" in t.lower() for t in sent_texts))
        self.assertTrue(any("degen" in t.lower() for t in sent_texts))

    def test_already_published_refuses_a_second_send(self):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_watchlist_only_package(review_dir, pick_id)
        os.environ["PICK_ID"] = pick_id
        os.makedirs(pw.PUBLISHED_DIR, exist_ok=True)
        with open(os.path.join(pw.PUBLISHED_DIR, pick_id + ".json"), "w") as f:
            json.dump({"telegram_watchlist": {"ok": True}}, f)

        with patch("post_telegram.post_text") as mock_post:
            pw.main()
            mock_post.assert_not_called()

    def test_checksum_mismatch_refuses_to_publish(self):
        pw.DRY_RUN = False
        pick_id = "2026-10-11_no-bet"
        review_dir = os.path.join(pw.REVIEW_ROOT, pick_id)
        _make_watchlist_only_package(review_dir, pick_id)
        os.environ["PICK_ID"] = pick_id
        self._seed_through_approval(pick_id)
        with open(os.path.join(review_dir, "watchlist-post.txt"), "w") as f:
            f.write("TAMPERED AFTER FREEZE")

        with patch("post_telegram.post_text") as mock_post:
            with self.assertRaises(SystemExit):
                pw.main()
            mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
