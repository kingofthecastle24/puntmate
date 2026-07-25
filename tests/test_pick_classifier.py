import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pick_classifier import Evidence, classify, classify_risk, classify_bet_type, is_backable, \
    RISK_STANDARD, RISK_RISKY, RISK_NO_BET, BET_INVESTOR, BET_PUNTER, BET_GAMBLER, BET_NO_BET, \
    MIN_EDGE_PCT, RISKY_MIN_EDGE_PCT, MIN_VALUE_EDGE_PCT


class BackabilityTests(unittest.TestCase):
    """2026-07-25 (Micah): NO_BET is no longer a pick classification. The
    'is this worth featuring at all' decision now lives in is_backable();
    classify_risk only ever returns STANDARD_PICK or RISKY_PICK."""

    def test_insufficient_evidence_is_not_backable(self):
        e = Evidence(evidence_sufficient=False, odds=2.0, our_probability=60, implied_probability=50, confidence="HIGH")
        backable, reason = is_backable(e)
        self.assertFalse(backable)
        self.assertIn("insufficient evidence", reason)

    def test_negative_edge_is_not_backable(self):
        # book prices it MORE likely than we do -> no genuine value -> dropped
        e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=48, implied_probability=50, confidence="HIGH")
        backable, reason = is_backable(e)
        self.assertFalse(backable)
        self.assertIn("no genuine value", reason)

    def test_slim_positive_edge_is_backable(self):
        # a 2% edge is now a real (if light) pick, never a no-bet
        e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=52, implied_probability=50, confidence="HIGH")
        backable, _ = is_backable(e)
        self.assertTrue(backable)

    def test_zero_edge_is_the_backable_floor(self):
        e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=50, implied_probability=50, confidence="HIGH")
        self.assertEqual(MIN_VALUE_EDGE_PCT, 0.0)
        self.assertTrue(is_backable(e)[0])


class RiskClassificationTests(unittest.TestCase):
    def test_classify_risk_never_returns_no_bet(self):
        # Even a wafer-thin win-market edge is STANDARD or RISKY, never NO_BET.
        for prob in (50.1, 52, 55, 60, 80):
            e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=prob, implied_probability=50, confidence="MODERATE")
            self.assertIn(classify_risk(e)[0], (RISK_STANDARD, RISK_RISKY))

    def test_thin_win_market_edge_is_risky(self):
        # edge 3% on a straight win market: below the 5% standard bar -> risky
        e = Evidence(evidence_sufficient=True, odds=2.20, our_probability=53, implied_probability=50, confidence="MODERATE")
        risk, reasons = classify_risk(e)
        self.assertEqual(risk, RISK_RISKY)
        self.assertTrue(any("below the standard" in r for r in reasons))

    def test_thin_edge_on_protective_market_is_standard(self):
        # SAME thin 3% edge but on a protective market (e.g. handicap/DNB):
        # lower variance, so it is an acceptable STANDARD pick, not risky.
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=53, implied_probability=50,
                     confidence="MODERATE", protective_market=True)
        self.assertEqual(classify_risk(e)[0], RISK_STANDARD)

    def test_handicap_is_not_auto_risky_at_a_big_price(self):
        # big price that would flag a WIN market risky is fine on a handicap
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=32,
                     confidence="MODERATE", protective_market=True)
        self.assertEqual(classify_risk(e)[0], RISK_STANDARD)

    def test_big_price_win_market_without_high_confidence_is_risky(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=32, confidence="MODERATE")
        self.assertEqual(classify_risk(e)[0], RISK_RISKY)

    def test_strong_evidence_is_standard(self):
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=60, implied_probability=50, confidence="HIGH", uncertainty_flags=[])
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_STANDARD)

    def test_low_confidence_pushes_to_risky_not_no_bet(self):
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=60, implied_probability=50, confidence="LOW")
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_RISKY)

    def test_outside_preferred_odds_alone_does_not_force_no_bet(self):
        # High odds, but HIGH confidence and sufficient evidence + edge clears bar -> still STANDARD
        e = Evidence(evidence_sufficient=True, odds=4.50, our_probability=40, implied_probability=25, confidence="HIGH", uncertainty_flags=[])
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_STANDARD)

    def test_high_odds_with_non_high_confidence_is_risky(self):
        e = Evidence(evidence_sufficient=True, odds=4.50, our_probability=40, implied_probability=25, confidence="MODERATE")
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_RISKY)

    def test_many_uncertainty_flags_push_to_risky(self):
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=60, implied_probability=50, confidence="HIGH",
                      uncertainty_flags=["a", "b"])
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_RISKY)


class BetTypeClassificationTests(unittest.TestCase):
    def test_no_bet_risk_forces_no_bet_type(self):
        e = Evidence(evidence_sufficient=False, odds=2.0, our_probability=60, implied_probability=50, confidence="LOW")
        self.assertEqual(classify_bet_type(RISK_NO_BET, e), BET_NO_BET)

    def test_short_odds_high_confidence_is_investor(self):
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=65, implied_probability=55, confidence="HIGH")
        self.assertEqual(classify_bet_type(RISK_STANDARD, e), BET_INVESTOR)

    def test_big_price_is_gambler_regardless_of_risk(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=30, confidence="HIGH")
        self.assertEqual(classify_bet_type(RISK_STANDARD, e), BET_GAMBLER)

    def test_gambler_can_be_standard_pick(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=45, implied_probability=30, confidence="HIGH", uncertainty_flags=[])
        c = classify(e)
        self.assertEqual(c.bet_type, BET_GAMBLER)
        self.assertEqual(c.risk, RISK_STANDARD)

    def test_investor_can_be_risky(self):
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=60, implied_probability=50, confidence="LOW")
        c = classify(e)
        self.assertEqual(c.risk, RISK_RISKY)
        # confidence LOW means it won't qualify for investor's HIGH-confidence bucket
        self.assertEqual(c.bet_type, BET_PUNTER)

    def test_middle_odds_is_punter(self):
        e = Evidence(evidence_sufficient=True, odds=2.40, our_probability=48, implied_probability=40, confidence="MODERATE")
        c = classify(e)
        self.assertEqual(c.bet_type, BET_PUNTER)


if __name__ == "__main__":
    unittest.main()
