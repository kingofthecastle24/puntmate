"""
Tests for the Instagram publish-reliability helpers added 2026-10-14 (Item
6): _request_with_retry (transient-failure retry on the Graph API calls,
which previously had none), _poll_container_status (replaces a blind
time.sleep(5)/time.sleep(3) before publish with an actual status_code
poll, mirroring post_instagram_story.py), and _alert_owner (an immediate
Telegram DM to the owner on a hard publish failure, on top of the
end-of-run result email).
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

os.environ.setdefault("INSTAGRAM_USER_ID", "17840000000000000")
os.environ.setdefault("INSTAGRAM_ACCESS_TOKEN", "test-token")

import post_instagram


def _resp(status_code=200, body=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = body or {}
    return r


class RequestWithRetryTests(unittest.TestCase):
    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_retries_on_connection_error_then_succeeds(self, mock_request, _sleep):
        import requests as requests_module
        ok = _resp(200, {"id": "123"})
        mock_request.side_effect = [requests_module.ConnectionError("boom"), ok]

        resp = post_instagram._request_with_retry("POST", "https://example.com")

        self.assertIs(resp, ok)
        self.assertEqual(mock_request.call_count, 2)

    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_retries_on_5xx_then_succeeds(self, mock_request, _sleep):
        ok = _resp(200, {"id": "123"})
        mock_request.side_effect = [_resp(503), ok]

        resp = post_instagram._request_with_retry("POST", "https://example.com")

        self.assertIs(resp, ok)
        self.assertEqual(mock_request.call_count, 2)

    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_does_not_retry_a_real_graph_api_error(self, mock_request, _sleep):
        # A 400 with an error payload is a rejection, not a glitch -- must
        # come straight back to the caller, not burn retries.
        error = _resp(400, {"error": {"code": 190}})
        mock_request.return_value = error

        resp = post_instagram._request_with_retry("POST", "https://example.com")

        self.assertIs(resp, error)
        self.assertEqual(mock_request.call_count, 1)

    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_gives_up_after_max_attempts(self, mock_request, _sleep):
        import requests as requests_module
        mock_request.side_effect = requests_module.Timeout("too slow")

        with self.assertRaises(requests_module.Timeout):
            post_instagram._request_with_retry("POST", "https://example.com", max_attempts=3)

        self.assertEqual(mock_request.call_count, 3)


class PollContainerStatusTests(unittest.TestCase):
    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_returns_true_once_finished(self, mock_request, _sleep):
        mock_request.side_effect = [
            _resp(200, {"status_code": "IN_PROGRESS"}),
            _resp(200, {"status_code": "FINISHED"}),
        ]
        self.assertTrue(post_instagram._poll_container_status("container123"))
        self.assertEqual(mock_request.call_count, 2)

    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_returns_false_on_error_status(self, mock_request, _sleep):
        mock_request.return_value = _resp(200, {"status_code": "ERROR"})
        self.assertFalse(post_instagram._poll_container_status("container123"))

    @patch("post_instagram.time.sleep")
    @patch("post_instagram.requests.request")
    def test_gives_up_and_still_returns_true_if_never_confirmed(self, mock_request, _sleep):
        # Never FINISHED or ERROR within the poll budget -- publish is still
        # attempted (a stuck status check shouldn't block a post that may
        # well have actually finished processing).
        mock_request.return_value = _resp(200, {"status_code": "IN_PROGRESS"})
        self.assertTrue(post_instagram._poll_container_status("container123"))
        self.assertEqual(mock_request.call_count, 6)


class AlertOwnerTests(unittest.TestCase):
    @patch("owner_dm.send_owner_dm")
    def test_sends_a_telegram_dm_with_the_failure_context(self, mock_send):
        post_instagram._alert_owner("carousel post", "some error detail")
        mock_send.assert_called_once()
        text = mock_send.call_args.args[0]
        self.assertIn("carousel post", text)
        self.assertIn("some error detail", text)

    @patch("owner_dm.send_owner_dm", side_effect=RuntimeError("telegram is down"))
    def test_never_raises_even_if_the_alert_itself_fails(self, _mock_send):
        try:
            post_instagram._alert_owner("feed post", "boom")
        except Exception as e:  # noqa: BLE001
            self.fail(f"_alert_owner must never raise, raised: {e}")


if __name__ == "__main__":
    unittest.main()
