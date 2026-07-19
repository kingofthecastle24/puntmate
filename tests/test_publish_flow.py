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


class TwoTierMultiPublishTests(unittest.TestCase):
    """2026-07-19 (Micah): Punter Multi + Gambler/Degenerate Multi each get
    their own Telegram post AND, when a graphic was rendered, their own
    Instagram feed carousel — independent per tier, never blocking anything
    else if one tier is missing or its graphic failed to render."""

    def setUp(self):
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", "test-channel")
        self.tmp = tempfile.mkdtemp()
        self.review_dir = os.path.join(self.tmp, "review", "2026-07-19_test-match")
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

    def _make_package_with_multis(self, punter_graphic=True, gambler_graphic=False, gambler_text=True):
        metadata = _make_review_package(self.review_dir)
        with open(os.path.join(self.review_dir, "punter-multi-post.txt"), "w") as f:
            f.write("PUNTER MULTI TEXT")
        if punter_graphic:
            for n in ("cover", "legs", "breakdown"):
                with open(os.path.join(self.review_dir, f"punter_multi_{n}.png"), "wb") as f:
                    f.write(b"FAKE")
        if gambler_text:
            with open(os.path.join(self.review_dir, "gambler-multi-post.txt"), "w") as f:
                f.write("GAMBLER MULTI TEXT")
        if gambler_graphic:
            for n in ("cover", "legs", "breakdown"):
                with open(os.path.join(self.review_dir, f"gambler_multi_{n}.png"), "wb") as f:
                    f.write(b"FAKE")
        return metadata

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_instagram_story.post_story_to_instagram")
    @patch("post_instagram.post_carousel_to_instagram")
    @patch("post_telegram.post_text")
    @patch("post_telegram.send_picks_card")
    def test_punter_multi_posts_to_telegram_and_instagram_when_graphic_present(
        self, mock_tg_card, mock_tg_text, mock_ig_feed, mock_ig_story, mock_email
    ):
        pp.DRY_RUN = False
        mock_tg_card.return_value = {"ok": True}
        mock_tg_text.return_value = {"ok": True}
        mock_ig_feed.return_value = True
        mock_ig_story.return_value = "media123"
        metadata = self._make_package_with_multis(punter_graphic=True, gambler_text=False)
        self._seed_state_through_approval(metadata["pick_id"])

        pp.main()

        mock_tg_text.assert_called_once_with("PUNTER MULTI TEXT")
        # Instagram feed gets called twice: once for the main pick, once for the punter multi.
        self.assertEqual(mock_ig_feed.call_count, 2)
        multi_call = mock_ig_feed.call_args_list[-1]
        self.assertEqual(multi_call.kwargs["caption"], "PUNTER MULTI TEXT")
        published = json.load(open(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        self.assertTrue(published["telegram_punter_multi"]["ok"])
        self.assertTrue(published["instagram_punter_multi"]["ok"])
        self.assertNotIn("telegram_gambler_multi", published)

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_instagram_story.post_story_to_instagram")
    @patch("post_instagram.post_carousel_to_instagram")
    @patch("post_telegram.post_text")
    @patch("post_telegram.send_picks_card")
    def test_tier_with_text_but_no_graphic_posts_telegram_only(
        self, mock_tg_card, mock_tg_text, mock_ig_feed, mock_ig_story, mock_email
    ):
        """render_multi_cards failing (e.g. Playwright hiccup) must never
        block that tier's Telegram post — it just has no Instagram card."""
        pp.DRY_RUN = False
        mock_tg_card.return_value = {"ok": True}
        mock_tg_text.return_value = {"ok": True}
        mock_ig_feed.return_value = True
        mock_ig_story.return_value = "media123"
        metadata = self._make_package_with_multis(punter_graphic=False, gambler_text=True, gambler_graphic=False)
        self._seed_state_through_approval(metadata["pick_id"])

        pp.main()

        published = json.load(open(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        self.assertTrue(published["telegram_punter_multi"]["ok"])
        self.assertTrue(published["telegram_gambler_multi"]["ok"])
        self.assertNotIn("instagram_punter_multi", published)
        self.assertNotIn("instagram_gambler_multi", published)
        # Instagram feed only called once — for the main pick, neither multi tier.
        self.assertEqual(mock_ig_feed.call_count, 1)

    def test_dry_run_reports_both_tiers_without_calling_any_platform(self):
        pp.DRY_RUN = True
        metadata = self._make_package_with_multis(punter_graphic=True, gambler_text=True, gambler_graphic=False)
        self._seed_state_through_approval(metadata["pick_id"])
        with patch("post_telegram.send_picks_card") as mock_tg, patch("post_telegram.post_text") as mock_tg_text:
            pp.main()
            mock_tg.assert_not_called()
            mock_tg_text.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))


if __name__ == "__main__":
    unittest.main()
