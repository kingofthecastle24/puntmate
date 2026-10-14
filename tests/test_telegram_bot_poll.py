"""
Tests for telegram_bot_poll.py -- the chat-driven multi-settle feature
(2026-10-12, Micah: "let me log/settle bets by chatting").

Covers: command parsing, the ambiguous/zero/one-candidate lookup logic,
chat_id filtering (only OWNER_CHAT_ID is ever acted on), offset persistence,
and the hard guarantee that this module can never post publicly.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import telegram_bot_poll as bot
import set_multi_result


class CommandParsingTests(unittest.TestCase):
    def test_help_commands(self):
        self.assertIn("Settle a weekend multi", bot.handle_text("/help"))
        self.assertIn("Settle a weekend multi", bot.handle_text("/start"))

    def test_unrecognised_text_returns_none(self):
        self.assertIsNone(bot.handle_text("what's the ROI this month"))
        self.assertIsNone(bot.handle_text(""))
        self.assertIsNone(bot.handle_text(None))

    def test_settle_regex_accepts_short_and_dated_forms_case_insensitively(self):
        m1 = bot.SETTLE_RE.match("/SETTLE Punter Win")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group(2).lower(), "punter")
        self.assertEqual(m1.group(3).lower(), "win")

        m2 = bot.SETTLE_RE.match("/settle 2026-08-07 degenerate void")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group(1), "2026-08-07")

    def test_settle_regex_rejects_bad_tier_or_result(self):
        self.assertIsNone(bot.SETTLE_RE.match("/settle banker win"))
        self.assertIsNone(bot.SETTLE_RE.match("/settle punter maybe"))


class LookupAndApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (bot.PUBLISHED_DIR, bot.MULTI_RESULTS_PATH, bot.OFFSET_PATH)
        bot.PUBLISHED_DIR = os.path.join(self.tmp, "published")
        bot.MULTI_RESULTS_PATH = os.path.join(self.tmp, "multi_results.json")
        bot.OFFSET_PATH = os.path.join(self.tmp, "state", "offset.json")
        os.makedirs(bot.PUBLISHED_DIR)
        set_multi_result.PATH = bot.MULTI_RESULTS_PATH

    def tearDown(self):
        bot.PUBLISHED_DIR, bot.MULTI_RESULTS_PATH, bot.OFFSET_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _publish(self, pick_id, tier, ok=True):
        path = os.path.join(bot.PUBLISHED_DIR, f"{pick_id}.json")
        with open(path, "w") as f:
            json.dump({f"telegram_{tier}_multi": {"ok": ok}}, f)

    def test_zero_candidates(self):
        pick_id, err = bot.find_target(None, "punter")
        self.assertIsNone(pick_id)
        self.assertIn("Nothing unsettled", err)

    def test_one_candidate_short_form_resolves(self):
        self._publish("2026-08-07_weekend_multi", "punter")
        pick_id, err = bot.find_target(None, "punter")
        self.assertEqual(pick_id, "2026-08-07_weekend_multi")
        self.assertIsNone(err)

    def test_multiple_candidates_require_dated_form(self):
        self._publish("2026-07-23_weekend_multi", "punter")
        self._publish("2026-08-07_weekend_multi", "punter")
        pick_id, err = bot.find_target(None, "punter")
        self.assertIsNone(pick_id)
        self.assertIn("More than one unsettled", err)
        self.assertIn("2026-07-23", err)
        self.assertIn("2026-08-07", err)

    def test_dated_form_disambiguates(self):
        self._publish("2026-07-23_weekend_multi", "punter")
        self._publish("2026-08-07_weekend_multi", "punter")
        pick_id, err = bot.find_target("2026-08-07", "punter")
        self.assertEqual(pick_id, "2026-08-07_weekend_multi")
        self.assertIsNone(err)

    def test_a_tier_that_never_published_is_not_a_candidate(self):
        self._publish("2026-08-07_weekend_multi", "punter", ok=False)
        pick_id, err = bot.find_target(None, "punter")
        self.assertIsNone(pick_id)
        self.assertIn("Nothing unsettled", err)

    def test_apply_settle_writes_result_and_removes_from_future_candidates(self):
        self._publish("2026-08-07_weekend_multi", "punter")
        reply = bot.apply_settle(None, "punter", "win")
        self.assertIn("Recorded", reply)
        self.assertIn("2026-08-07_weekend_multi", reply)

        with open(bot.MULTI_RESULTS_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["2026-08-07_weekend_multi"]["punter"], "win")

        # Now settled -- no longer an unsettled candidate.
        pick_id, err = bot.find_target(None, "punter")
        self.assertIsNone(pick_id)
        self.assertIn("Nothing unsettled", err)

    def test_full_handle_text_round_trip(self):
        self._publish("2026-08-07_weekend_multi", "degenerate")
        reply = bot.handle_text("/settle degenerate loss")
        self.assertIn("Recorded", reply)
        with open(bot.MULTI_RESULTS_PATH) as f:
            saved = json.load(f)
        self.assertEqual(saved["2026-08-07_weekend_multi"]["degenerate"], "loss")


class OffsetPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_offset = bot.OFFSET_PATH
        bot.OFFSET_PATH = os.path.join(self.tmp, "state", "offset.json")

    def tearDown(self):
        bot.OFFSET_PATH = self._orig_offset
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_offset_defaults_to_zero_then_persists(self):
        self.assertEqual(bot.load_offset(), 0)
        bot.save_offset(42)
        self.assertEqual(bot.load_offset(), 42)


class PollOnceSecurityTests(unittest.TestCase):
    """poll_once() must only ever act on OWNER_CHAT_ID, and must always
    advance the offset past every update it saw -- including ones it
    ignored -- so a stranger's messages can't make it requeue forever."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (bot.PUBLISHED_DIR, bot.MULTI_RESULTS_PATH, bot.OFFSET_PATH)
        bot.PUBLISHED_DIR = os.path.join(self.tmp, "published")
        bot.MULTI_RESULTS_PATH = os.path.join(self.tmp, "multi_results.json")
        bot.OFFSET_PATH = os.path.join(self.tmp, "state", "offset.json")
        os.makedirs(bot.PUBLISHED_DIR)
        set_multi_result.PATH = bot.MULTI_RESULTS_PATH
        self._publish("2026-08-07_weekend_multi", "punter")

    def tearDown(self):
        bot.PUBLISHED_DIR, bot.MULTI_RESULTS_PATH, bot.OFFSET_PATH = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _publish(self, pick_id, tier, ok=True):
        path = os.path.join(bot.PUBLISHED_DIR, f"{pick_id}.json")
        with open(path, "w") as f:
            json.dump({f"telegram_{tier}_multi": {"ok": ok}}, f)

    @patch("telegram_bot_poll.send_reply")
    @patch("requests.get")
    def test_message_from_a_stranger_is_ignored_but_offset_still_advances(self, mock_get, mock_reply):
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: {"result": [
            {"update_id": 5, "message": {"chat": {"id": 999999}, "text": "/settle punter win"}}
        ]}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "OWNER_CHAT_ID": "12345"}):
            bot.poll_once()

        mock_reply.assert_not_called()
        self.assertEqual(bot.load_offset(), 5)
        # Nothing was settled by the stranger's message.
        self.assertFalse(os.path.exists(bot.MULTI_RESULTS_PATH))

    @patch("telegram_bot_poll.send_reply")
    @patch("requests.get")
    def test_message_from_owner_is_processed_and_replied_to(self, mock_get, mock_reply):
        mock_get.return_value.raise_for_status = lambda: None
        mock_get.return_value.json = lambda: {"result": [
            {"update_id": 6, "message": {"chat": {"id": 12345}, "text": "/settle punter win"}}
        ]}
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "OWNER_CHAT_ID": "12345"}):
            bot.poll_once()

        mock_reply.assert_called_once()
        reply_text = mock_reply.call_args[0][2]
        self.assertIn("Recorded", reply_text)
        self.assertEqual(bot.load_offset(), 6)


class NeverTouchesPublicPlatformsTests(unittest.TestCase):
    def test_module_never_imports_a_public_poster(self):
        src = open(bot.__file__).read()
        self.assertNotIn("post_instagram", src)
        self.assertNotIn("post_facebook", src)
        self.assertNotIn("post_telegram", src)  # public-channel poster, not send_reply

    def test_module_never_reads_a_meta_secret(self):
        src = open(bot.__file__).read()
        for forbidden in ("META_PAGE_TOKEN", "FACEBOOK_PAGE_TOKEN", "INSTAGRAM_ACCESS_TOKEN"):
            self.assertNotIn(forbidden, src)


if __name__ == "__main__":
    unittest.main()
