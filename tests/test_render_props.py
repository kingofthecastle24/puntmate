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


if __name__ == "__main__":
    unittest.main()
