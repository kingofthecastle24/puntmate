"""
Tests for post_instagram.post_degen_watch_to_instagram (2026-10-11,
Micah): a single-image post with a caller-supplied caption (Degen
Watch's own, already validated through the strictest responsible-
gambling check) -- never post_picks_to_instagram's build_caption(), and
shares the same upload/container/publish flow and LAST_ERROR capture as
every other path in this module (confirmed via the same code-190 fix-hint
behaviour test_meta_error_capture.py already covers for the other paths).

2026-10-14 (Item 6): image hosting moved from Imgur to catbox.moe and the
blind time.sleep() before publish became a status_code poll -- tests mock
upload_to_catbox and requests.request (used by _request_with_retry) and
stub out _poll_container_status so the retry/poll mechanics themselves
(covered by their own tests) don't need re-deriving here.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INSTAGRAM_USER_ID", "17840000000000000")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "test-token")

import post_instagram


class PostDegenWatchToInstagramTests(unittest.TestCase):
    def setUp(self):
        post_instagram.LAST_ERROR = None
        post_instagram.IG_USER_ID = "17840000000000000"
        post_instagram.IG_TOKEN = "test-token"

    @patch("post_instagram._poll_container_status", return_value=True)
    @patch("post_instagram.requests.request")
    @patch("post_instagram.upload_to_catbox")
    @patch("post_instagram.os.path.exists", return_value=True)
    def test_success_posts_the_caller_supplied_caption(self, _mock_exists, mock_upload, mock_request, _mock_poll):
        mock_upload.return_value = "https://files.catbox.moe/fake.png"
        container_resp = MagicMock(); container_resp.json.return_value = {"id": "container123"}
        publish_resp = MagicMock(); publish_resp.json.return_value = {"id": "post123"}
        mock_request.side_effect = [container_resp, publish_resp]

        ok = post_instagram.post_degen_watch_to_instagram("fake.png", "DEGEN WATCH — unofficial caption text")

        self.assertTrue(ok)
        container_call = mock_request.call_args_list[0]
        self.assertEqual(container_call.kwargs["data"]["caption"], "DEGEN WATCH — unofficial caption text")
        self.assertIsNone(post_instagram.LAST_ERROR)

    @patch("post_instagram.os.path.exists", return_value=False)
    def test_missing_image_file_returns_false_without_calling_the_api(self, _mock_exists):
        with patch("post_instagram.requests.request") as mock_request:
            ok = post_instagram.post_degen_watch_to_instagram("missing.png", "caption")
            self.assertFalse(ok)
            mock_request.assert_not_called()

    @patch("post_instagram.os.path.exists", return_value=True)
    @patch("post_instagram.upload_to_catbox", side_effect=RuntimeError("catbox.moe upload failed: no response"))
    def test_upload_failure_returns_false(self, _mock_upload, _mock_exists):
        with patch("post_instagram.requests.request") as mock_request:
            ok = post_instagram.post_degen_watch_to_instagram("fake.png", "caption")
            self.assertFalse(ok)
            mock_request.assert_not_called()

    @patch("post_instagram.requests.request")
    @patch("post_instagram.upload_to_catbox")
    @patch("post_instagram.os.path.exists", return_value=True)
    def test_token_death_is_captured_with_the_same_fix_hint_as_other_paths(self, _mock_exists, mock_upload, mock_request):
        mock_upload.return_value = "https://files.catbox.moe/fake.png"
        error_resp = MagicMock()
        error_resp.json.return_value = {"error": {
            "message": "Error validating access token.", "type": "OAuthException", "code": 190, "error_subcode": 467,
        }}
        mock_request.return_value = error_resp

        ok = post_instagram.post_degen_watch_to_instagram("fake.png", "caption")

        self.assertFalse(ok)
        self.assertIsNotNone(post_instagram.LAST_ERROR)
        self.assertEqual(post_instagram.LAST_ERROR.get("code"), 190)
        self.assertIn("META_PAGE_TOKEN", post_instagram.LAST_ERROR.get("fix", ""))

    @patch("post_instagram.IG_USER_ID", "")
    def test_unconfigured_credentials_skip_without_calling_the_api(self):
        with patch("post_instagram.requests.request") as mock_request:
            ok = post_instagram.post_degen_watch_to_instagram("fake.png", "caption")
            self.assertFalse(ok)
            mock_request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
