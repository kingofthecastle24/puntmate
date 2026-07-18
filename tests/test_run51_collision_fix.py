"""
Regression tests for the run #51 crash (2026-07-18): a same-day re-run
(scheduled 8am run, ~12 min after a manual live run) independently selected
the same fixture an earlier run that day had already carried through to a
live pick_id. Live pick_ids are date+slugified-match only (no per-run
suffix), so the second run computed an identical pick_id to one that
already had state. send_preview.py's first call —
workflow_state.transition(pick_id, GENERATED) — is only valid when a
pick_id has no existing state, so this raised InvalidTransitionError,
uncaught, and crashed the generate job (exit code 1), which then cascaded
into the publish job failing on a missing artifact.

Two layers tested here, matching the fix:
  1. main.py: a fixture that already has ANY state recorded today is
     converted to NO_BET before a pick_id is ever computed for it — the
     collision never reaches send_preview.py in the first place.
  2. send_preview.py: even if a collision somehow reaches it anyway,
     _safe_transition() catches InvalidTransitionError and no-ops with a
     warning instead of raising.
"""
import os, sys, json, shutil, tempfile, unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import main as pm_main
import send_preview
from workflow_state import transition, GENERATED, PUBLISHED, AWAITING_APPROVAL


SAMPLE_MATCH = {
    "match": "Seattle Mariners vs San Francisco Giants",
    "sport_label": "MLB",
    "sport": "baseball_mlb",
    "kickoff": "2026-07-18T02:00:00Z",
}

SAMPLE_PICK = {
    "has_pick": True,
    "match": SAMPLE_MATCH["match"],
    "selection": "Mariners to Win",
    "odds": "1.75",
    "market": "Head to Head",
    "sport_label": "MLB",
    "bet_type": "INVESTOR_BET",
    "bet_type_label": "INVESTOR",
    "risk": "STANDARD_PICK",
    "confidence": "HIGH",
    "final_explanation": "Clean edge here.",
    "research_warnings": [],
}


class MainDedupeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR)
        pm_main.REPO_ROOT = self.tmp
        pm_main.LATEST_RUN_PATH = os.path.join(self.tmp, "data", "latest_run.json")
        pm_main.CARDS_DIR = os.path.join(self.tmp, "data", "cards")

    def tearDown(self):
        pm_main.REPO_ROOT, pm_main.LATEST_RUN_PATH, pm_main.CARDS_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _seed_state(self, pick_id, state):
        transition(self.tmp, pick_id, GENERATED)
        # Fast-forward through whatever states are needed; PUBLISHED needs
        # the full chain per workflow_state's VALID_TRANSITIONS.
        if state != GENERATED:
            from workflow_state import PREVIEW_READY, APPROVED, PUBLISHING
            transition(self.tmp, pick_id, PREVIEW_READY)
            if state != PREVIEW_READY:
                transition(self.tmp, pick_id, AWAITING_APPROVAL)
                if state == PUBLISHED:
                    transition(self.tmp, pick_id, APPROVED)
                    transition(self.tmp, pick_id, PUBLISHING)
                    transition(self.tmp, pick_id, PUBLISHED)

    @patch("generate_pick.generate_pick_for_matches", return_value=dict(SAMPLE_PICK))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_same_day_republish_of_same_fixture_converts_to_no_bet(self, *_mocks):
        run_date = "2026-07-18"
        from render_brand_templates import slugify
        live_pick_id = f"{run_date}_{slugify(SAMPLE_MATCH['match'])}"
        self._seed_state(live_pick_id, PUBLISHED)

        with patch("main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = run_date
            mock_dt.now.return_value.isoformat.return_value = f"{run_date}T08:00:00+00:00"
            # run() calls render_card only when has_pick stays True — it
            # should NOT reach that far, so no need to mock the renderer.
            pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)

        self.assertFalse(saved["pick"]["has_pick"])
        self.assertIn("already went through today's pipeline", saved["pick"]["reasoning"])
        self.assertIn("watchlist", saved)  # falls through the normal NO_BET+watchlist path

    @patch("generate_pick.generate_pick_for_matches", return_value=dict(SAMPLE_PICK))
    @patch("fetch_news.fetch_news", return_value={"warnings": []})
    @patch("fetch_odds.fetch_upcoming_odds", return_value=[SAMPLE_MATCH])
    def test_first_run_of_the_day_is_unaffected(self, *_mocks):
        """No prior state for this fixture today -> dedupe guard is a no-op,
        pick proceeds normally (falls through to card rendering, which we
        let fail over to the legacy renderer / NO_BET path harmlessly since
        we're not testing rendering here)."""
        run_date = "2026-07-18"
        with patch("main.datetime") as mock_dt:
            mock_dt.now.return_value.strftime.return_value = run_date
            mock_dt.now.return_value.isoformat.return_value = f"{run_date}T08:00:00+00:00"
            with patch.object(pm_main, "render_card", return_value={"ok": True, "files": {}}):
                pm_main.run()

        with open(pm_main.LATEST_RUN_PATH) as f:
            saved = json.load(f)
        self.assertTrue(saved["pick"]["has_pick"])
        self.assertEqual(saved["pick"]["match"], SAMPLE_MATCH["match"])


class SendPreviewSafeTransitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig = (send_preview.REPO_ROOT, send_preview.REVIEW_ROOT)
        send_preview.REPO_ROOT = self.tmp
        send_preview.REVIEW_ROOT = os.path.join(self.tmp, "data", "review")

    def tearDown(self):
        send_preview.REPO_ROOT, send_preview.REVIEW_ROOT = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_safe_transition_no_ops_on_collision_instead_of_raising(self):
        pick_id = "2026-07-18_collision_test"
        transition(self.tmp, pick_id, GENERATED)  # pick_id already has state

        # This is exactly what run #51 did uncaught -> InvalidTransitionError.
        # It must now return False and NOT raise.
        result = send_preview._safe_transition(pick_id, GENERATED, note="review package built")
        self.assertFalse(result)

    def test_safe_transition_succeeds_on_fresh_pick_id(self):
        pick_id = "2026-07-18_fresh_test"
        result = send_preview._safe_transition(pick_id, GENERATED, note="review package built")
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
