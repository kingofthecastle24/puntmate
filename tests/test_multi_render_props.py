import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from render_brand_templates import build_multi_props, MULTI_TIER_CONFIG


def _legs():
    return [
        {"match": "A vs B", "sport_label": "NRL", "selection": "A", "market": "Head to Head", "odds": "1.80"},
        {"match": "C vs D", "sport_label": "NRL", "selection": "UNDER 7", "market": "Total", "odds": "2.00"},
        {"match": "E vs F", "sport_label": "AFL", "selection": "E -6.5", "market": "Handicap", "odds": "1.90"},
    ]


class BuildMultiPropsTests(unittest.TestCase):
    def test_unknown_tier_rejected(self):
        with self.assertRaises(ValueError):
            build_multi_props(_legs(), "yolo")  # not a configured tier

    def test_punter_tier_props(self):
        props = build_multi_props(_legs(), "punter")
        self.assertEqual(props["multiType"], "Punter Multi")
        self.assertEqual(props["stake"], "$20")  # 2026-07-19 (Micah): $20 Punter / $5 Gambler-Degenerate
        self.assertEqual(props["palette"], "green")
        self.assertIn("A vs B | A | Head to Head | 1.80", props["legs"])
        self.assertEqual(len(props["legs"].split("\n")), 3)

    def test_gambler_tier_props_use_five_dollar_stake(self):
        """Micah's ask: 'a $5 multi where you can make close to $1000' —
        the illustrative stake lives on the graphic only (the template
        auto-computes stakeReturn from stake x combined odds); it is
        deliberately never written into the Telegram/Instagram TEXT copy."""
        props = build_multi_props(_legs(), "gambler")
        self.assertEqual(props["multiType"], "Gambler Multi")
        self.assertEqual(props["stake"], "$5")
        self.assertEqual(props["palette"], "pink")
        self.assertNotIn("stakeReturn", props)  # left to the template to compute

    def test_legs_text_survives_pipe_round_trip(self):
        """Each line must parse back into exactly 4 pipe-delimited fields —
        the format the Multi.dc.html template's own JS parser expects
        (match | selection | market | odds)."""
        props = build_multi_props(_legs(), "punter")
        for line in props["legs"].split("\n"):
            parts = [p.strip() for p in line.split("|")]
            self.assertEqual(len(parts), 4, line)

    def test_all_tiers_configured(self):
        self.assertEqual(set(MULTI_TIER_CONFIG.keys()), {"punter", "gambler", "degenerate"})


if __name__ == "__main__":
    unittest.main()
