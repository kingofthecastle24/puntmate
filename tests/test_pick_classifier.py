import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pick_classifier import Evidence, classify, classify_risk, classify_bet_type, \
    RISK_STANDARD, RISK_RISKY, RISK_NO_BET, BET_INVESTOR, BET_PUNTER, BET_GAMBLER, BET_NO_BET


class RiskClassificationTests(unittest.TestCase):
    def test_insufficient_evidence_is_no_bet(self):
        e = Evidence(evidence_sufficient=False, odds=2.0, our_probability=60, implied_probability=50, confidence="HIGH")
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_NO_BET)

    def test_edge_below_minimum_is_no_bet(self):
        e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=52, implied_probability=50, confidence="HIGH")
        risk, _ = classify_risk(e)
        self.assertEqual(risk, RISK_NO_BET)

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
