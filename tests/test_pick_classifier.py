import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from pick_classifier import Evidence, classify, classify_risk, classify_bet_type, is_backable, \
    RISK_STANDARD, RISK_RISKY, RISK_NO_BET, BET_INVESTOR, BET_PUNTER, BET_GAMBLER, BET_NO_BET, \
    MIN_EDGE_PCT, RISKY_MIN_EDGE_PCT, MIN_VALUE_EDGE_PCT, GAMBLER_MIN_VALUE_EDGE_PCT, \
    INVESTOR_MIN_PROB_PCT, PUNTER_MIN_PROB_PCT


class BackabilityTests(unittest.TestCase):
    """2026-10-14 (Micah): per-lane gate. is_backable(evidence, bet_type) now
    needs the lane -- investor/punter select on model probability, gambler
    keeps the old value-edge bar. Every lane still requires sufficient
    evidence and a non-negative edge."""

    def test_insufficient_evidence_is_not_backable(self):
        e = Evidence(evidence_sufficient=False, odds=2.0, our_probability=60, implied_probability=50, confidence="HIGH")
        backable, reason = is_backable(e, BET_PUNTER)
        self.assertFalse(backable)
        self.assertIn("insufficient evidence", reason)

    def test_negative_edge_is_not_backable_for_any_lane(self):
        # book prices it MORE likely than we do -> no genuine value -> dropped,
        # whatever lane it would otherwise land in.
        e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=48, implied_probability=50, confidence="HIGH")
        for bet_type in (BET_INVESTOR, BET_PUNTER, BET_GAMBLER):
            backable, reason = is_backable(e, bet_type)
            self.assertFalse(backable, msg=bet_type)
            self.assertIn("is below the book's implied probability", reason)

    def test_gambler_thin_edge_below_the_restored_floor_is_not_backable(self):
        # a 2% edge no longer clears the restored 7% value-betting floor on
        # the gambler lane (PICK_ANALYST_SKILL.md's old "quality over
        # quantity" philosophy, now scoped to this one lane).
        e = Evidence(evidence_sufficient=True, odds=3.00, our_probability=52, implied_probability=50, confidence="HIGH")
        backable, reason = is_backable(e, BET_GAMBLER)
        self.assertFalse(backable)
        # BUG FIX regression (2026-10-11, flagged by external audit): 52%
        # genuinely IS above 50% — the old wording ("is not above") was
        # simply false here. A thin-but-real edge must say so honestly,
        # not claim there's no edge at all.
        self.assertIn("only 2.0 points above", reason)
        self.assertIn("short of the 7% floor", reason)
        self.assertNotIn("is below", reason)
        self.assertNotIn("is not above", reason)

    def test_gambler_edge_at_the_floor_is_backable(self):
        e = Evidence(evidence_sufficient=True, odds=3.00, our_probability=57, implied_probability=50, confidence="HIGH")
        self.assertEqual(GAMBLER_MIN_VALUE_EDGE_PCT, 7.0)
        self.assertEqual(MIN_VALUE_EDGE_PCT, 7.0)  # old alias still equals the gambler floor
        self.assertTrue(is_backable(e, BET_GAMBLER)[0])

    def test_investor_below_probability_floor_is_not_backable(self):
        # odds qualify for the investor lane, but 65% model probability is
        # below the 70% bar -- not about edge size at all.
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=65, implied_probability=55, confidence="HIGH")
        backable, reason = is_backable(e, BET_INVESTOR)
        self.assertFalse(backable)
        self.assertIn("70% bar for investor picks", reason)

    def test_investor_at_the_probability_floor_is_backable(self):
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=70, implied_probability=55, confidence="MODERATE")
        self.assertEqual(INVESTOR_MIN_PROB_PCT, 70.0)
        self.assertTrue(is_backable(e, BET_INVESTOR)[0])

    def test_punter_below_probability_floor_is_not_backable(self):
        e = Evidence(evidence_sufficient=True, odds=2.30, our_probability=55, implied_probability=45, confidence="MODERATE")
        backable, reason = is_backable(e, BET_PUNTER)
        self.assertFalse(backable)
        self.assertIn("60% bar for punter picks", reason)

    def test_punter_at_the_probability_floor_is_backable(self):
        e = Evidence(evidence_sufficient=True, odds=2.30, our_probability=60, implied_probability=45, confidence="MODERATE")
        self.assertEqual(PUNTER_MIN_PROB_PCT, 60.0)
        self.assertTrue(is_backable(e, BET_PUNTER)[0])


class RiskClassificationTests(unittest.TestCase):
    def test_classify_risk_never_returns_no_bet(self):
        # Even a wafer-thin win-market edge is STANDARD or RISKY, never NO_BET.
        for prob in (50.1, 52, 55, 60, 80):
            e = Evidence(evidence_sufficient=True, odds=2.0, our_probability=prob, implied_probability=50, confidence="MODERATE")
            self.assertIn(classify_risk(e, BET_PUNTER)[0], (RISK_STANDARD, RISK_RISKY))

    def test_thin_win_market_edge_is_risky_for_punter(self):
        # edge 3% on a straight win market: below the 5% standard bar -> risky
        e = Evidence(evidence_sufficient=True, odds=2.20, our_probability=53, implied_probability=50, confidence="MODERATE")
        risk, reasons = classify_risk(e, BET_PUNTER)
        self.assertEqual(risk, RISK_RISKY)
        self.assertTrue(any("below the standard" in r for r in reasons))

    def test_same_thin_edge_is_not_risky_for_investor(self):
        # 2026-10-14: the investor lane selects on model probability, not
        # edge size, so a small edge is the norm there, not a risk signal --
        # the SAME evidence that's risky for punter is standard for investor.
        e = Evidence(evidence_sufficient=True, odds=2.20, our_probability=53, implied_probability=50, confidence="MODERATE")
        risk, reasons = classify_risk(e, BET_INVESTOR)
        self.assertEqual(risk, RISK_STANDARD)

    def test_thin_edge_on_protective_market_is_standard(self):
        # SAME thin 3% edge but on a protective market (e.g. handicap/DNB):
        # lower variance, so it is an acceptable STANDARD pick, not risky.
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=53, implied_probability=50,
                     confidence="MODERATE", protective_market=True)
        self.assertEqual(classify_risk(e, BET_PUNTER)[0], RISK_STANDARD)

    def test_handicap_is_not_auto_risky_at_a_big_price(self):
        # big price that would flag a WIN market risky is fine on a handicap
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=32,
                     confidence="MODERATE", protective_market=True)
        self.assertEqual(classify_risk(e, BET_GAMBLER)[0], RISK_STANDARD)

    def test_big_price_win_market_without_high_confidence_is_risky(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=32, confidence="MODERATE")
        self.assertEqual(classify_risk(e, BET_GAMBLER)[0], RISK_RISKY)

    def test_strong_evidence_is_standard(self):
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=60, implied_probability=50, confidence="HIGH", uncertainty_flags=[])
        risk, _ = classify_risk(e, BET_PUNTER)
        self.assertEqual(risk, RISK_STANDARD)

    def test_low_confidence_pushes_to_risky_not_no_bet(self):
        # The low-confidence signal is NOT lane-specific -- applies to investor too.
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=72, implied_probability=50, confidence="LOW")
        risk, _ = classify_risk(e, BET_INVESTOR)
        self.assertEqual(risk, RISK_RISKY)

    def test_outside_preferred_odds_alone_does_not_force_no_bet(self):
        # High odds, but HIGH confidence and sufficient evidence + edge clears bar -> still STANDARD
        e = Evidence(evidence_sufficient=True, odds=4.50, our_probability=40, implied_probability=25, confidence="HIGH", uncertainty_flags=[])
        risk, _ = classify_risk(e, BET_GAMBLER)
        self.assertEqual(risk, RISK_STANDARD)

    def test_high_odds_with_non_high_confidence_is_risky(self):
        e = Evidence(evidence_sufficient=True, odds=4.50, our_probability=40, implied_probability=25, confidence="MODERATE")
        risk, _ = classify_risk(e, BET_GAMBLER)
        self.assertEqual(risk, RISK_RISKY)

    def test_many_uncertainty_flags_push_to_risky(self):
        e = Evidence(evidence_sufficient=True, odds=1.90, our_probability=60, implied_probability=50, confidence="HIGH",
                      uncertainty_flags=["a", "b"])
        risk, _ = classify_risk(e, BET_PUNTER)
        self.assertEqual(risk, RISK_RISKY)


class BetTypeClassificationTests(unittest.TestCase):
    def test_no_bet_risk_forces_no_bet_type(self):
        e = Evidence(evidence_sufficient=False, odds=2.0, our_probability=60, implied_probability=50, confidence="LOW")
        self.assertEqual(classify_bet_type(RISK_NO_BET, e), BET_NO_BET)

    def test_short_odds_with_70pct_probability_is_investor_regardless_of_confidence_label(self):
        # 2026-10-14 (Micah, decided): Investor = odds <= 2.20 AND model win
        # probability >= 70%, NOT gated on the HIGH confidence label. The
        # research validator caps confidence at MODERATE below 3 sources,
        # which was starving this exact lane on a genuinely strong pick.
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=74, implied_probability=55, confidence="MODERATE")
        self.assertEqual(classify_bet_type(RISK_STANDARD, e), BET_INVESTOR)

    def test_short_odds_but_below_70pct_probability_is_not_investor(self):
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=65, implied_probability=55, confidence="HIGH")
        self.assertEqual(classify_bet_type(RISK_STANDARD, e), BET_PUNTER)

    def test_big_price_is_gambler_regardless_of_risk(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=40, implied_probability=30, confidence="HIGH")
        self.assertEqual(classify_bet_type(RISK_STANDARD, e), BET_GAMBLER)

    def test_gambler_can_be_standard_pick(self):
        e = Evidence(evidence_sufficient=True, odds=3.20, our_probability=45, implied_probability=30, confidence="HIGH", uncertainty_flags=[])
        c = classify(e)
        self.assertEqual(c.bet_type, BET_GAMBLER)
        self.assertEqual(c.risk, RISK_STANDARD)

    def test_investor_can_still_be_risky_via_low_confidence(self):
        # Low confidence is a risk signal regardless of lane -- investor is
        # no exception, even though its thin-edge signal is suppressed.
        e = Evidence(evidence_sufficient=True, odds=1.80, our_probability=72, implied_probability=55, confidence="LOW")
        c = classify(e)
        self.assertEqual(c.bet_type, BET_INVESTOR)
        self.assertEqual(c.risk, RISK_RISKY)

    def test_middle_odds_is_punter(self):
        e = Evidence(evidence_sufficient=True, odds=2.40, our_probability=48, implied_probability=40, confidence="MODERATE")
        c = classify(e)
        self.assertEqual(c.bet_type, BET_PUNTER)


if __name__ == "__main__":
    unittest.main()
