"""
Tests for the PROPOSED conservative-mode selection strategy (2026-10-11,
external audit item 4). See scripts/conservative_mode.py's module docstring
-- this is NOT wired into main.py's live run; these tests exercise the
mechanism Micah asked to have built and reviewed, independent of whether/
when it's ever turned on.
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pick_classifier import Evidence, classify
from conservative_mode import select_conservative, CONSERVATIVE_MIN_PROBABILITY


def _candidate(match, odds, our_probability, implied_probability, confidence, protective_market=False):
    evidence = Evidence(
        evidence_sufficient=True,
        odds=odds,
        our_probability=our_probability,
        implied_probability=implied_probability,
        confidence=confidence,
        protective_market=protective_market,
    )
    return {
        "match_meta": {"match": match},
        "evidence": evidence,
        "verdict": classify(evidence),
    }


class ConservativeModeSelectionTests(unittest.TestCase):
    def test_default_threshold_is_the_documented_proposed_value(self):
        # Pins the exact number under review so a silent edit shows up as
        # a failing test, not a quiet behaviour change.
        self.assertEqual(CONSERVATIVE_MIN_PROBABILITY, 65.0)

    def test_short_odds_alone_does_not_qualify_without_high_probability(self):
        # 1.30 is about as short as odds get -- but if our own estimate is
        # only just barely above the book's (a thin edge), that is NOT
        # "safe" and must not be selected just because the price is short.
        c = _candidate("A vs B", odds=1.30, our_probability=58, implied_probability=52, confidence="MODERATE")
        self.assertIsNone(select_conservative([c]))

    def test_long_odds_with_strong_evidence_and_high_probability_does_qualify(self):
        # The exact case the brief calls out: "allow prices below 1.50 but
        # never equate low odds with safety" -- also means the reverse: a
        # LONGER price with genuinely strong evidence is not excluded just
        # for not being short.
        c = _candidate("C vs D", odds=3.40, our_probability=70, implied_probability=29, confidence="HIGH")
        picked = select_conservative([c])
        self.assertIsNotNone(picked)
        self.assertEqual(picked["match_meta"]["match"], "C vs D")

    def test_moderate_confidence_never_qualifies_regardless_of_probability(self):
        # Confidence is an evidence-strength ceiling set by research
        # validation, not something a high probability number can buy past.
        c = _candidate("E vs F", odds=1.60, our_probability=80, implied_probability=50, confidence="MODERATE")
        self.assertIsNone(select_conservative([c]))

    def test_below_threshold_probability_never_qualifies_even_at_high_confidence(self):
        c = _candidate("G vs H", odds=1.70, our_probability=64.9, implied_probability=50, confidence="HIGH")
        self.assertIsNone(select_conservative([c]))

    def test_at_threshold_probability_exactly_qualifies(self):
        c = _candidate("I vs J", odds=1.70, our_probability=65.0, implied_probability=50, confidence="HIGH")
        self.assertIsNotNone(select_conservative([c]))

    def test_highest_probability_wins_among_multiple_qualifiers(self):
        low = _candidate("K vs L", odds=1.60, our_probability=66, implied_probability=50, confidence="HIGH")
        high = _candidate("M vs N", odds=2.80, our_probability=78, implied_probability=40, confidence="HIGH")
        picked = select_conservative([low, high])
        self.assertEqual(picked["match_meta"]["match"], "M vs N")

    def test_nothing_qualifying_is_an_honest_no_bet_not_a_fallback_pick(self):
        c = _candidate("O vs P", odds=1.40, our_probability=55, implied_probability=52, confidence="MODERATE")
        self.assertIsNone(select_conservative([c]))

    def test_empty_candidate_list_is_a_no_bet(self):
        self.assertIsNone(select_conservative([]))

    def test_threshold_is_overridable_for_calibration_without_editing_the_module(self):
        c = _candidate("Q vs R", odds=2.00, our_probability=60, implied_probability=50, confidence="HIGH")
        self.assertIsNone(select_conservative([c]))  # fails the live 65% default
        self.assertIsNotNone(select_conservative([c], min_probability=55.0))  # a lower, exploratory threshold


if __name__ == "__main__":
    unittest.main()
