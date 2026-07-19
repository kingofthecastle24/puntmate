"""
Tests for the send_preview.py and publish_pick.py branches that handle a
weekend-multi-only post (is_weekend_multi=True, has_pick=False) — 2026-07-19.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import send_preview as sp
import publish_pick as pp
from workflow_state import load_state, GENERATED, PREVIEW_READY, AWAITING_APPROVAL


def _weekend_metadata(has_punter=True, has_gambler=False, pick_id="2026-07-24_weekend_multi"):
    metadata = {
        "has_pick": False,
        "is_weekend_multi": True,
        "pick_id": pick_id,
        "post_date": "2026-07-24",
        "run_id": "1",
        "research_warnings": [],
        "intended_platforms": [],
    }
    if has_punter:
        metadata["has_punter_multi"] = True
        metadata["intended_platforms"] = sorted(set(metadata["intended_platforms"]) | {"telegram"})
    if has_gambler:
        metadata["has_gambler_multi"] = True
        metadata["intended_platforms"] = sorted(set(metadata["intended_platforms"]) | {"telegram"})
    return metadata


class SendPreviewWeekendMultiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (sp.REPO_ROOT, sp.REVIEW_ROOT)
        sp.REPO_ROOT = self.tmp
        sp.REVIEW_ROOT = os.path.join(self.tmp, "review")

    def tearDown(self):
        sp.REPO_ROOT, sp.REVIEW_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_package(self, metadata, punter_text="PUNTER TEXT", gambler_text=None):
        review_dir = os.path.join(sp.REVIEW_ROOT, metadata["pick_id"])
        os.makedirs(review_dir, exist_ok=True)
        if metadata.get("has_punter_multi"):
            with open(os.path.join(review_dir, "punter-multi-post.txt"), "w") as f:
                f.write(punter_text)
        if metadata.get("has_gambler_multi") and gambler_text:
            with open(os.path.join(review_dir, "gambler-multi-post.txt"), "w") as f:
                f.write(gambler_text)
        with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
            json.dump(metadata, f)
        return review_dir

    @patch("send_preview.email_service.send_weekend_multi_email")
    def test_qualifying_weekend_multi_reaches_awaiting_approval(self, mock_email):
        metadata = _weekend_metadata(has_punter=True, has_gambler=True)
        self._write_package(metadata, gambler_text="GAMBLER TEXT")
        os.environ["PICK_ID"] = metadata["pick_id"]

        sp.main()

        state = load_state(sp.REPO_ROOT, metadata["pick_id"])
        self.assertEqual(state["state"], AWAITING_APPROVAL)
        mock_email.assert_called_once()
        args = mock_email.call_args.args
        self.assertIn("PUNTER TEXT", args[2])
        self.assertIn("GAMBLER TEXT", args[3])

    @patch("send_preview.email_service.send_weekend_multi_email")
    def test_neither_tier_clearing_never_enters_approval_gate(self, mock_email):
        metadata = {
            "has_pick": False, "is_weekend_multi": True, "pick_id": "2026-07-24_weekend_multi",
            "post_date": "2026-07-24", "run_id": "1", "research_warnings": [],
        }
        self._write_package(metadata)
        os.environ["PICK_ID"] = metadata["pick_id"]

        sp.main()

        state = load_state(sp.REPO_ROOT, metadata["pick_id"])
        self.assertEqual(state["state"], PREVIEW_READY)  # never reaches AWAITING_APPROVAL
        mock_email.assert_not_called()


class PublishWeekendMultiTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", "test-channel")
        self.tmp = tempfile.mkdtemp()
        self._orig = (pp.REPO_ROOT, pp.REVIEW_ROOT, pp.PUBLISHED_DIR, pp.DRY_RUN)
        pp.REPO_ROOT = self.tmp
        pp.REVIEW_ROOT = os.path.join(self.tmp, "review")
        pp.PUBLISHED_DIR = os.path.join(self.tmp, "published")

    def tearDown(self):
        pp.REPO_ROOT, pp.REVIEW_ROOT, pp.PUBLISHED_DIR, pp.DRY_RUN = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_package(self, metadata, punter_text="PUNTER TEXT"):
        review_dir = os.path.join(pp.REVIEW_ROOT, metadata["pick_id"])
        os.makedirs(review_dir, exist_ok=True)
        with open(os.path.join(review_dir, "punter-multi-post.txt"), "w") as f:
            f.write(punter_text)
        with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
            json.dump(metadata, f)

        from manifest import build_manifest, write_manifest
        manifest = build_manifest(review_dir, ["punter-multi-post.txt", "post-metadata.json"], extra={"pick_id": metadata["pick_id"]})
        write_manifest(manifest, os.path.join(review_dir, "manifest.json"))
        return review_dir

    def _seed_state_through_approval(self, pick_id):
        from workflow_state import transition
        transition(pp.REPO_ROOT, pick_id, GENERATED)
        transition(pp.REPO_ROOT, pick_id, PREVIEW_READY)
        transition(pp.REPO_ROOT, pick_id, AWAITING_APPROVAL)

    @patch("publish_pick.email_service.send_result_email")
    @patch("post_telegram.post_text")
    def test_weekend_multi_publishes_without_a_blank_main_post(self, mock_tg_text, mock_email):
        pp.DRY_RUN = False
        mock_tg_text.return_value = {"ok": True}
        metadata = _weekend_metadata(has_punter=True, has_gambler=False)
        self._write_package(metadata)
        self._seed_state_through_approval(metadata["pick_id"])
        os.environ["REVIEW_DIR"] = os.path.join(pp.REVIEW_ROOT, metadata["pick_id"])

        pp.main()

        # Only the tier-specific call fires; no attempt at a blank "main" post.
        mock_tg_text.assert_called_once_with("PUNTER TEXT")
        published = json.load(open(os.path.join(pp.PUBLISHED_DIR, metadata["pick_id"] + ".json")))
        self.assertTrue(published["telegram_punter_multi"]["ok"])
        self.assertNotIn("telegram", published)  # no main-post key at all

    def test_has_pick_false_alone_no_longer_blocks_a_weekend_multi(self):
        """The old 'if not has_pick: return' check would have silently
        skipped this entirely -- has_punter_multi/has_gambler_multi must
        now also be checked."""
        pp.DRY_RUN = True
        metadata = _weekend_metadata(has_punter=True)
        self._write_package(metadata)
        self._seed_state_through_approval(metadata["pick_id"])
        os.environ["REVIEW_DIR"] = os.path.join(pp.REVIEW_ROOT, metadata["pick_id"])

        # Should reach the dry-run report path, not bail out early.
        with patch("builtins.print") as mock_print:
            pp.main()
        printed = "\n".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertNotIn("NO_BET — nothing to publish.", printed)


if __name__ == "__main__":
    unittest.main()
