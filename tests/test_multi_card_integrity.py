import os, re, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from render_brand_templates import build_multi_props, render_multi, MAX_MULTI_TEMPLATE_LEGS


def _leg(match, selection, odds, sport="UFC", market="Head to Head"):
    return {"match": match, "sport_label": sport, "selection": selection, "market": market, "odds": odds}


# The exact leg set from the 2026-11-06 weekend punter multi
# (data/latest_weekend_run.json): its cards rendered with only the first 5
# legs and a blank combined-odds field while the Telegram text correctly
# listed all 7 at combined 7.10.
UFC_7_LEGS = [
    _leg("Tatiana Suarez vs Virna Jandiroba", "OVER 2.5", "1.23", market="Total"),
    _leg("Waldo Cortes-Acosta vs Johnny Walker", "WALDO CORTES-ACOSTA", "1.48"),
    _leg("Austin Bashi vs Carlos Calderon", "AUSTIN BASHI", "1.21"),
    _leg("Davey Grant vs Elijah Smith", "ELIJAH SMITH", "1.33"),
    _leg("Karine Silva vs Gabriella Fernandes", "KARINE SILVA", "1.46"),
    _leg("Andre Petroski vs Mantas Kondratavicius", "MANTAS KONDRATAVICIUS", "1.36"),
    _leg("Priscila Cachoeira vs Nina Milošević", "NINA MILOŠEVIĆ", "1.22"),
]


class CombinedOddsPropsTests(unittest.TestCase):
    def test_combined_odds_passed_explicitly(self):
        """Regression 2026-11-06: the template's combinedOdds schema default
        is "", which its ?? fallback does not fall through, so cards printed
        a blank "Combined at .". Props must carry the value computed from the
        same legs the text post uses (1.23*1.48*1.21*1.33*1.46*1.36*1.22
        = 7.097 -> "7.10", matching the published Telegram text)."""
        props = build_multi_props(UFC_7_LEGS, "punter")
        self.assertEqual(props["combinedOdds"], "7.10")

    def test_combined_odds_three_legs(self):
        legs = [_leg("A vs B", "A", "1.30"), _leg("C vs D", "C", "1.04"), _leg("E vs F", "E", "1.05")]
        props = build_multi_props(legs, "punter")
        self.assertEqual(props["combinedOdds"], "1.42")  # 1.30*1.04*1.05 = 1.4196

    def test_unpriced_leg_omits_prop(self):
        """If any leg has no numeric odds we must not guess - leave the prop
        unset so the template's own fallback applies rather than printing a
        wrong figure."""
        legs = [_leg("A vs B", "A", "1.30"), _leg("C vs D", "C", "1.04"), _leg("E vs F", "E", "TBD")]
        props = build_multi_props(legs, "punter")
        self.assertNotIn("combinedOdds", props)


class TemplateCapacityGuardTests(unittest.TestCase):
    def test_over_cap_render_raises_before_any_browser_work(self):
        """A multi the template cannot show completely must never render:
        missing graphics are handled cleanly downstream (Telegram-only),
        truncated ones would publish cards that disagree with the data."""
        with self.assertRaises(ValueError) as ctx:
            render_multi({"match": "Weekend Multi"}, "punter", UFC_7_LEGS)
        self.assertIn(str(MAX_MULTI_TEMPLATE_LEGS), str(ctx.exception))

    def test_guard_constant_matches_template_cap(self):
        """The template JS hard-caps its leg parser with .slice(0, N); if the
        template's cap ever changes, this constant must move with it."""
        template = os.path.join(
            os.path.dirname(__file__), "..", "brand", "Templates",
            "PuntMate Bet Post - Multi.dc.html",
        )
        with open(template, encoding="utf-8") as f:
            m = re.search(r"\.slice\(0,\s*(\d+)\)", f.read())
        self.assertIsNotNone(m, "template leg cap not found - re-check the guard")
        self.assertEqual(int(m.group(1)), MAX_MULTI_TEMPLATE_LEGS)


if __name__ == "__main__":
    unittest.main()
