import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from copy_validator import (
    validate_text, validate_post, CopyValidationError,
    check_no_bet_contradiction, check_gambler_rg, check_staking_language, check_tone,
    check_internal_leak,
)


class ToneAndStakingTests(unittest.TestCase):
    def test_banned_corporate_phrase_rejected(self):
        with self.assertRaises(CopyValidationError):
            validate_text("Strong capital allocation opportunity here.", risk="STANDARD_PICK")

    def test_staking_language_rejected(self):
        with self.assertRaises(CopyValidationError):
            validate_text("Put 2 units on this one.", risk="STANDARD_PICK")

    def test_dollar_bankroll_percentage_rejected(self):
        self.assertTrue(len(check_staking_language("Risk 5% of your bankroll on this.")) > 0)

    def test_clean_mate_tone_passes(self):
        text = "This one's a solid touch — the price still pays and the form backs it up."
        validate_text(text, risk="STANDARD_PICK")  # should not raise


class NoBetContradictionTests(unittest.TestCase):
    def test_no_bet_phrase_on_standard_pick_is_rejected(self):
        hits = check_no_bet_contradiction("No pick meets my criteria today, sitting this one out.", "STANDARD_PICK")
        self.assertTrue(len(hits) > 0)

    def test_no_bet_phrase_on_risky_pick_is_rejected(self):
        hits = check_no_bet_contradiction("Sitting this one out.", "RISKY_PICK")
        self.assertTrue(len(hits) > 0)

    def test_no_bet_phrase_fine_when_risk_is_no_bet(self):
        hits = check_no_bet_contradiction("Sitting this one out.", "NO_BET")
        self.assertEqual(hits, [])


class ResponsibleGamblingTests(unittest.TestCase):
    def test_gambler_guaranteed_win_language_rejected(self):
        hits = check_gambler_rg("This is a guaranteed win, go all in.", "GAMBLER_BET")
        self.assertTrue(len(hits) >= 2)

    def test_gambler_normal_copy_passes(self):
        hits = check_gambler_rg("Bold call at a big price — this is a swing, not a certainty.", "GAMBLER_BET")
        self.assertEqual(hits, [])

    def test_rg_check_skipped_for_non_gambler(self):
        hits = check_gambler_rg("Guaranteed win, all in.", "INVESTOR_BET")
        self.assertEqual(hits, [])


class FullPostValidationTests(unittest.TestCase):
    def test_multiple_picks_rejected(self):
        meta = {"risk": "STANDARD_PICK", "bet_type": "PUNTER_BET", "picks": [{"a": 1}, {"b": 2}]}
        with self.assertRaises(CopyValidationError):
            validate_post(meta, "clean text", "clean text")

    def test_no_bet_with_selection_field_rejected(self):
        meta = {"classification": "NO_BET", "selection": "TEAM A"}
        with self.assertRaises(CopyValidationError):
            validate_post(meta, "", "")

    def test_internal_research_warning_leak_rejected(self):
        meta = {"risk": "STANDARD_PICK", "bet_type": "PUNTER_BET"}
        with self.assertRaises(CopyValidationError):
            validate_post(meta, "Research warning: limited sources.", "clean")

    def test_clean_post_passes(self):
        meta = {"risk": "STANDARD_PICK", "bet_type": "PUNTER_BET"}
        self.assertTrue(validate_post(meta, "Solid touch tonight, the value's real.", "Solid touch tonight, the value's real."))


class IncidentInternalLeakTests(unittest.TestCase):
    """Regression coverage for the 2026-07-17 incident: a real live Telegram
    post shipped reading 'Worth knowing: Warriors news snippet references
    Cowboys not Dragons — possible copy-paste from different week; Dragons
    form unknown beyond general knowledge.' The old INTERNAL_ONLY_PHRASES
    list didn't contain anything matching this wording, so check_internal_leak
    found nothing and it went out live. These tests prove the exact leaked
    text (and closely related phrasing) is now caught, while genuine
    punter-facing caveats still pass clean."""

    def test_exact_leaked_sentence_is_rejected(self):
        leaked = (
            "Worth knowing: Warriors news snippet references Cowboys not Dragons — "
            "possible copy-paste from different week; Dragons form unknown beyond general knowledge."
        )
        hits = check_internal_leak(leaked)
        self.assertTrue(len(hits) > 0, "the exact incident sentence must be caught")

    def test_exact_leaked_sentence_fails_full_validation(self):
        meta = {"risk": "RISKY_PICK", "bet_type": "INVESTOR_BET"}
        leaked_telegram_text = (
            "The market has Warriors at 83% but honestly this feels light. "
            "Worth knowing: Warriors news snippet references Cowboys not Dragons — "
            "possible copy-paste from different week; Dragons form unknown beyond general knowledge."
        )
        with self.assertRaises(CopyValidationError):
            validate_post(meta, leaked_telegram_text, "clean caption")

    def test_related_source_mixup_phrasing_also_caught(self):
        variants = [
            "Worth knowing: this news article might be about a different fixture entirely.",
            "Worth knowing: couldn't verify this snippet, might be a mismatched source.",
            "Worth knowing: possible mix-up, the report references the wrong team.",
        ]
        for text in variants:
            with self.subTest(text=text):
                self.assertTrue(len(check_internal_leak(text)) > 0)

    def test_genuine_punter_facing_caveats_still_pass_clean(self):
        legit = [
            "Worth knowing: star fullback is a late fitness doubt; wet weather forecast for kickoff.",
            "Worth knowing: the Dragons have lost their last four on the road.",
            "Keep this one light — the value's there but so is the uncertainty.",
        ]
        for text in legit:
            with self.subTest(text=text):
                self.assertEqual(check_internal_leak(text), [])


if __name__ == "__main__":
    unittest.main()
