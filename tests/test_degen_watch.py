"""
Tests for Degen Watch (2026-10-11, Micah): on a genuine no-bet day, the
candidate closest to clearing the 7% value bar is still surfaced --
explicitly unofficial, never the real PuntMate pick, never counted toward
the public strike rate or any ledger. Covers:
  - generate_pick.select_closest_to_passing (the selection logic)
  - render_brand_templates.build_degen_watch_props (card data mapping)
  - build_review_package.build_degen_watch_text (Telegram copy + the
    public-copy validation gates it must pass)
"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from generate_pick import select_closest_to_passing
from render_brand_templates import build_degen_watch_props
from build_review_package import build_degen_watch_text
from copy_validator import check_internal_leak, check_staking_language, check_gambler_rg, validate_text


def _not_backable(match, edge_pct, evidence_sufficient=True, our_probability=54.0, implied_probability=50.0, odds=2.10, selection="X to Win"):
    return {
        "cause": "not_backable",
        "match": match,
        "sport_label": "NRL",
        "market_type": "h2h",
        "selection": selection,
        "odds": odds,
        "reason": "edge too thin to back",
        "evidence_sufficient": evidence_sufficient,
        "our_probability": our_probability,
        "implied_probability": implied_probability,
        "edge_pct": edge_pct,
        "min_value_edge_pct": 7.0,
    }


class SelectClosestToPassingTests(unittest.TestCase):
    def test_picks_the_highest_edge_among_qualifying_rejections(self):
        candidates = [
            _not_backable("A vs B", edge_pct=2.0),
            _not_backable("C vs D", edge_pct=5.5),
            _not_backable("E vs F", edge_pct=4.1),
        ]
        picked = select_closest_to_passing(candidates)
        self.assertEqual(picked["match"], "C vs D")

    def test_insufficient_evidence_rejections_never_qualify(self):
        # No genuine edge to show for "the model couldn't assess this at
        # all" -- a high edge_pct here would be meaningless, not a
        # near-miss.
        candidates = [
            _not_backable("A vs B", edge_pct=6.9, evidence_sufficient=False),
        ]
        self.assertIsNone(select_closest_to_passing(candidates))

    def test_unresolved_odds_and_hallucinated_match_rejections_never_qualify(self):
        candidates = [
            {"cause": "unresolved_odds", "match": "A vs B", "market_type": "h2h", "reason": "x"},
            {"cause": "hallucinated_match", "match": "C vs D", "reason": "x"},
        ]
        self.assertIsNone(select_closest_to_passing(candidates))

    def test_empty_list_is_none(self):
        self.assertIsNone(select_closest_to_passing([]))

    def test_mixed_causes_only_considers_not_backable_with_sufficient_evidence(self):
        candidates = [
            {"cause": "unresolved_odds", "match": "Z vs Y", "market_type": "h2h", "reason": "x"},
            _not_backable("A vs B", edge_pct=1.0, evidence_sufficient=False),
            _not_backable("C vs D", edge_pct=3.3),
        ]
        picked = select_closest_to_passing(candidates)
        self.assertEqual(picked["match"], "C vs D")


class BuildDegenWatchPropsTests(unittest.TestCase):
    def test_maps_candidate_fields_into_template_props(self):
        candidate = _not_backable("Warriors vs Storm", edge_pct=4.2, our_probability=54.0, implied_probability=50.0, odds=2.10, selection="Storm to Win")
        props = build_degen_watch_props(candidate)
        self.assertEqual(props["matchup"], "Warriors vs Storm")
        self.assertEqual(props["sportTag"], "NRL")
        self.assertEqual(props["selection"], "Storm to Win")
        self.assertEqual(props["odds"], "2.10")
        self.assertEqual(props["edge"], "+4.2%")
        self.assertEqual(props["ourProbability"], "54%")
        self.assertEqual(props["impliedProbability"], "50%")

    def test_negative_looking_but_still_rejected_edge_formats_with_sign(self):
        # Shouldn't normally reach here (select_closest_to_passing only
        # returns real near-misses), but the formatter itself should still
        # be honest about sign if ever called with a small edge directly.
        candidate = _not_backable("A vs B", edge_pct=0.4)
        props = build_degen_watch_props(candidate)
        self.assertEqual(props["edge"], "+0.4%")


class BuildDegenWatchTextTests(unittest.TestCase):
    def test_text_names_the_candidate_and_is_explicitly_unofficial(self):
        candidate = _not_backable("Warriors vs Storm", edge_pct=4.2, selection="Storm to Win", odds=2.10)
        text = build_degen_watch_text(candidate, "2026-10-11")
        self.assertIn("DEGEN WATCH", text)
        self.assertIn("UNOFFICIAL", text)
        self.assertIn("NOT a PuntMate pick", text)
        self.assertIn("Storm to Win", text)
        self.assertIn("2.1", text)

    def test_text_passes_internal_leak_and_staking_language_gates(self):
        candidate = _not_backable("Warriors vs Storm", edge_pct=4.2)
        text = build_degen_watch_text(candidate, "2026-10-11")
        self.assertEqual(check_internal_leak(text), [])
        self.assertEqual(check_staking_language(text), [])

    def test_text_passes_the_strictest_gambler_rg_check(self):
        candidate = _not_backable("Warriors vs Storm", edge_pct=4.2)
        text = build_degen_watch_text(candidate, "2026-10-11")
        self.assertEqual(check_gambler_rg(text, "GAMBLER_BET"), [])

    def test_text_passes_the_full_validate_text_gate_as_built(self):
        # Matches exactly how build_review_package.main validates it:
        # risk=None (not NO_BET -- this post DOES carry a selection/odds),
        # bet_type forced to GAMBLER_BET regardless of the real classification.
        candidate = _not_backable("Warriors vs Storm", edge_pct=4.2)
        text = build_degen_watch_text(candidate, "2026-10-11")
        validate_text(text, risk=None, bet_type="GAMBLER_BET", public=True)  # must not raise


if __name__ == "__main__":
    unittest.main()
