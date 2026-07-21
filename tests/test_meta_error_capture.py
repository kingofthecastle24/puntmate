"""Tests for the Meta API error capture added 2026-07-21 (run #58 incident:
Instagram failed with OAuthException code 190 'session invalid' but the
publish record only said ok:False — the real error was buried in run logs).
post_instagram/post_instagram_story must record LAST_ERROR, and token-death
(code 190) must carry an actionable fix hint into the record."""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INSTAGRAM_USER_ID", "17840000000000000")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "test-token")

import post_instagram
import post_instagram_story


def _meta_error_response(code=190, subcode=467):
    resp = MagicMock()
    resp.json.return_value = {"error": {
        "message": "Error validating access token: The session is invalid because the user logged out.",
        "type": "OAuthException", "code": code, "error_subcode": subcode,
    }}
    return resp


class CarouselErrorCaptureTests(unittest.TestCase):
    def setUp(self):
        post_instagram.LAST_ERROR = None
        post_instagram.IG_USER_ID = "17840000000000000"
        post_instagram.IG_TOKEN = "test-token"

    @patch("post_instagram.requests.post")
    def test_dead_token_records_error_with_fix_hint(self, mock_post):
        mock_post.return_value = _meta_error_response()
        ok = post_instagram.post_carousel_to_instagram(
            slide_paths=["a.png"], caption="cap",
            slide_urls=["https://example.com/a.png"],
        )
        self.assertFalse(ok)
        self.assertIsNotNone(post_instagram.LAST_ERROR)
        self.assertEqual(post_instagram.LAST_ERROR.get("code"), 190)
        # the code-190 fix hint is what makes the record actionable
        self.assertIn("META_PAGE_TOKEN", post_instagram.LAST_ERROR.get("fix", ""))

    @patch("post_instagram.requests.post")
    def test_success_leaves_no_error(self, mock_post):
        ok_resp = MagicMock(); ok_resp.json.return_value = {"id": "123"}
        mock_post.return_value = ok_resp
        with patch("post_instagram.time.sleep"):
            post_instagram.post_carousel_to_instagram(
                slide_paths=["a.png"], caption="cap",
                slide_urls=["https://example.com/a.png"],
            )
        self.assertIsNone(post_instagram.LAST_ERROR)


class StoryErrorCaptureTests(unittest.TestCase):
    def setUp(self):
        post_instagram_story.LAST_ERROR = None

    @patch("post_instagram_story.requests.post")
    def test_story_container_error_is_recorded(self, mock_post):
        mock_post.return_value = _meta_error_response()
        with patch.object(post_instagram_story, "IG_USER_ID", "17840000000000000"), \
             patch.object(post_instagram_story, "IG_TOKEN", "test-token"):
            media_id = post_instagram_story.post_story_to_instagram("https://example.com/story.png")
        self.assertIsNone(media_id)
        self.assertIsNotNone(post_instagram_story.LAST_ERROR)
        self.assertEqual(post_instagram_story.LAST_ERROR.get("code"), 190)


if __name__ == "__main__":
    unittest.main()
