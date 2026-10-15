import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from render_brand_templates import build_props


def _pick(**overrides):
    base = {
        "match": "Warriors vs Storm",
        "sport": "rugbyleague_nrl",
        "sport_label": "NRL",
        "selection": "WARRIORS",
        "market": "Head to Head",
        "odds": "1.90",
        "bet_type": "INVESTOR_BET",
        "risk": "STANDARD_PICK",
        "confidence_label": "HIGH",
        "final_explanation": "Warriors have won four straight at home.",
        "bet_type_reason": "This one's about as close to a sure thing as sport gets.",
    }
    base.update(overrides)
    return base


class BuildPropsTests(unittest.TestCase):
    def test_no_staking_fields_introduced(self):
        props = build_props(_pick())
        for banned in ("stake", "stakeReturn", "unit", "units", "bankroll"):
            self.assertNotIn(banned, props)

    def test_risk_tagline_carries_bet_type_without_new_template_field(self):
        props = build_props(_pick())
        self.assertIn("Bet type: Investor", props["riskTagline"])
        self.assertIn("Standard Pick", props["riskTagline"])

    def test_existing_prop_keys_preserved(self):
        props = build_props(_pick())
        expected_keys = {"matchup", "sportTag", "market", "selection", "selectionShort", "odds",
                          "oddsNote", "insight", "competition", "analysis", "confidence",
                          "confidenceLabel", "riskTagline", "handle", "coverTheme"}
        self.assertEqual(expected_keys, set(props.keys()))

    def test_long_selection_still_truncated(self):
        long_name = "A" * 80
        props = build_props(_pick(selection=long_name))
        self.assertLessEqual(len(props["selection"]), 45)

    def test_legacy_pick_key_still_supported(self):
        pick = {"match": "A vs B", "pick": "TEAM A", "sport_label": "NRL", "odds": "2.00", "reasoning": "n/a", "confidence": "Medium"}
        props = build_props(pick)
        self.assertEqual(props["selection"], "TEAM A")


    def test_long_insight_truncates_at_sentence_boundary_not_mid_word(self):
        """Same class of bug as the France vs England Telegram post (see
        test_generate_pick.py's TruncationRegressionTests): the card's
        'insight' prop used to naive-slice at exactly 140 chars with no
        word-boundary handling at all. Now it goes through the same shared
        text_format.truncate_at_sentence used for the public post text."""
        long_explanation = (
            "Warriors have won four straight at home. Their forward pack has "
            "been dominant in the middle third all season and Broncos have "
            "struggled defensively on the road."
        )
        props = build_props(_pick(final_explanation=long_explanation))
        insight = props["insight"]
        self.assertLessEqual(len(insight), 141)
        self.assertTrue(insight.endswith(".") or insight.endswith("…"))

    def test_short_insight_left_untouched(self):
        short = "Warriors have won four straight at home."
        props = build_props(_pick(final_explanation=short))
        self.assertEqual(props["insight"], short)


class ResearchOnlyPropsTests(unittest.TestCase):
    """2026-10-15 redesign, Section 7: a RESEARCH_ONLY lead must never
    show a model probability/edge, or claim an Investor/Punter/Gambler
    tier or a confidence level it didn't earn through the real gate --
    enforced here at the prop-mapping layer, with zero changes to the
    approved .dc.html templates themselves."""

    def _research_only_pick(self, **overrides):
        base = {
            "content_mode": "RESEARCH_ONLY",
            "match": "Warriors vs Storm",
            "sport": "rugbyleague_nrl",
            "sport_label": "NRL",
            "selection": "WARRIORS",
            "market": "h2h",
            "odds": 1.9,
            "bet_type": None,
            "risk": None,
            "confidence": None,
            "confidence_label": None,
            "final_explanation": "Warriors have won four straight at home.",
        }
        base.update(overrides)
        return base

    def test_never_carries_bet_type_or_tier_wording(self):
        props = build_props(self._research_only_pick())
        tagline_lower = props["riskTagline"].lower()
        for banned in ("investor", "punter", "gambler", "bet type:"):
            self.assertNotIn(banned, tagline_lower)

    def test_tagline_is_honest_about_not_being_gated(self):
        props = build_props(self._research_only_pick())
        self.assertIn("not a gated pick", props["riskTagline"].lower())

    def test_cover_theme_never_becomes_a_value_claim(self):
        # "Value Alert" is a real enum option on the approved templates --
        # must never be selected for a research-only lead.
        props = build_props(self._research_only_pick())
        self.assertNotEqual(props["coverTheme"], "Value Alert")

    def test_confidence_label_renders_naturally_in_the_fixed_template_text(self):
        # The templates render exactly "{confidenceLabel} RISK" -- must
        # still read sensibly, and "HIGH RISK" is literally true for an
        # ungated lead.
        props = build_props(self._research_only_pick())
        self.assertEqual(props["confidenceLabel"], "HIGH")

    def test_gated_pick_is_unaffected_by_the_research_only_branch(self):
        gated = build_props(_pick())  # content_mode absent -> normal gated path
        self.assertIn("Bet type: Investor", gated["riskTagline"])
        self.assertEqual(gated["confidenceLabel"], "HIGH")


if __name__ == "__main__":
    unittest.main()
