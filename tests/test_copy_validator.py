import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from copy_validator import (
    validate_text, validate_post, CopyValidationError,
    check_no_bet_contradiction, check_gambler_rg, check_staking_language, check_tone,
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


if __name__ == "__main__":
    unittest.main()
