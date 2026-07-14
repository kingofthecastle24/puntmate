import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import publish_pick as pp
from manifest import build_manifest, write_manifest
from workflow_state import transition, load_state, GENERATED, PREVIEW_READY, AWAITING_APPROVAL, REJECTED, PUBLISHED, \
    PARTIALLY_PUBLISHED, PUBLISH_FAILED


def _make_review_package(review_dir, metadata_extra=None, tamper=False):
    os.makedirs(review_dir, exist_ok=True)
    with open(os.path.join(review_dir, "telegram-post.txt"), "w") as f:
        f.write("Solid touch tonight, the value's real.")
    with open(os.path.join(review_dir, "instagram-caption.txt"), "w") as f:
        f.write("Solid touch tonight, the value's real.")
    for name in ("cover.png", "tip.png", "breakdown.png", "story.png"):
        with open(os.path.join(review_dir, name), "wb") as f:
            f.write(b"FAKE")
    metadata = {
        "has_pick": True,
        "pick_id": "2026-07-15_test-match",
        "match": "Warriors vs Storm",
        "selection": "WARRIORS",
        "odds": "1.90",
        "bet_type": "INVESTOR_BET",
        "risk": "STANDARD_PICK",
        "intended_platforms": ["telegram", "instagram_feed", "instagram_story", "facebook"],
        "carousel_urls": ["http://example.com/1.png"],
        "story_url": "http://example.com/story.png",
        "post_date": "2026-07-15",
        "run_id": "1",
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
        json.dump(metadata, f)

    manifest_files = ["telegram-post.txt", "instagram-caption.txt", "post-metadata.json", "cover.png", "tip.png", "breakdown.png", "story.png"]
    manifest = build_manifest(review_dir, manifest_files, extra={"pick_id": metadata["pick_id"]})
    write_manifest(manifest, os.path.join(review_dir, "manifest.json"))

    if tamper:
        with open(os.path.join(review_dir, "telegram-post.txt"), "w") as f:
            f.write("TAMPERED AFTER APPROVAL")

    return metadata


class PublishFlowTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", "test-channel")
        self.tmp = tempfile.mkdtemp()
        self.review_dir = os.path.join(self.tmp, "review", "2026-07-15_test-match")
        self._orig = (pp.REPO_ROOT, pp.REVIEW_ROOT, pp.PUBLISHED_DIR, pp.DRY_RUN)
        pp.REPO_ROOT = self.tmp
        pp.REVIEW_ROOT = os.path.join(self.tmp, "review")
        pp.PUBLISHED_DIR = os.path.join(self.tmp, "published")
        os.environ["REVIEW_DIR"] = self.review_dir

    def tearDown(self):
        pp.REPO_ROOT, pp.REVIEW_ROOT, pp.PUBLISHED_DIR, pp.DRY_RUN = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_state_through_approval(self, pick_id):
        transition(pp.REPO_ROOT, pick_id, GENERATED)
        transition(pp.REPO_ROOT, pick_id, PREVIEW_READY)
        transition(pp.REPO_ROOT, pick_id, AWAITING_APPROVAL)

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_instagram_story.post_story_to_instagram")
    @patch("post_instagram.post_carousel_to_instagram")
    @patch("post_telegram.send_picks_card")
    def test_all_platforms_succeed_marks_published_and_facebook_via_instagram(
        self, mock_tg, mock_ig_feed, mock_ig_story, mock_email
    ):
        pp.DRY_RUN = False
        metadata = _make_review_package(self.review_dir)
        self._seed_state_through_approval(metadata["pick_id"])
        mock_tg.return_value = {"ok": True}
        mock_ig_feed.return_value = True
        mock_ig_story.return_value = "media123"

        pp.main()

        state = load_state(pp.REPO_ROOT, metadata["pick_id"])
        self.assertEqual(state["state"], PUBLISHED)
        published = json.load(open(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        self.assertEqual(published["facebook"]["status"], "via_linked_instagram")
        self.assertTrue(mock_email.called)

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_instagram_story.post_story_to_instagram")
    @patch("post_instagram.post_carousel_to_instagram")
    @patch("post_telegram.send_picks_card")
    def test_instagram_failure_keeps_telegram_success_partial_published(
        self, mock_tg, mock_ig_feed, mock_ig_story, mock_email
    ):
        pp.DRY_RUN = False
        metadata = _make_review_package(self.review_dir)
        self._seed_state_through_approval(metadata["pick_id"])
        mock_tg.return_value = {"ok": True}
        mock_ig_feed.side_effect = Exception("Instagram API down")
        mock_ig_story.return_value = "media123"

        pp.main()
        published = json.load(open(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        self.assertTrue(published["telegram"]["ok"])
        self.assertFalse(published["instagram_feed"]["ok"])
        state = load_state(pp.REPO_ROOT, metadata["pick_id"])
        self.assertEqual(state["state"], PARTIALLY_PUBLISHED)

    @patch("publish_pick.email_service.send_result_email")
    def test_checksum_mismatch_blocks_publish_entirely(self, mock_email):
        pp.DRY_RUN = False
        metadata = _make_review_package(self.review_dir, tamper=True)
        self._seed_state_through_approval(metadata["pick_id"])

        with self.assertRaises(SystemExit):
            pp.main()

        self.assertFalse(os.path.exists(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        state = load_state(pp.REPO_ROOT, metadata["pick_id"])
        self.assertEqual(state["state"], PUBLISH_FAILED)

    def test_dry_run_never_calls_any_platform(self):
        pp.DRY_RUN = True
        metadata = _make_review_package(self.review_dir)
        self._seed_state_through_approval(metadata["pick_id"])
        with patch("post_telegram.send_picks_card") as mock_tg:
            pp.main()
            mock_tg.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_instagram_story.post_story_to_instagram")
    @patch("post_instagram.post_carousel_to_instagram")
    @patch("post_telegram.send_picks_card")
    def test_rejected_pick_cannot_later_be_published(self, mock_tg, mock_ig_feed, mock_ig_story, mock_email):
        metadata = _make_review_package(self.review_dir)
        self._seed_state_through_approval(metadata["pick_id"])
        transition(pp.REPO_ROOT, metadata["pick_id"], REJECTED)

        from workflow_state import InvalidTransitionError
        with self.assertRaises(InvalidTransitionError):
            transition(pp.REPO_ROOT, metadata["pick_id"], PUBLISHED)


if __name__ == "__main__":
    unittest.main()
