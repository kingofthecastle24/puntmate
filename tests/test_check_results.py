"""Tests for check_results.py — the nightly results settler.

Added 2026-07-21 after a coverage review found this module at 0% despite
being the thing that writes wins/losses into the PUBLIC record every night
(recap strike rate, dashboard, challenge balance all flow from it). The
review also found a real bug, fixed alongside: totals landing exactly on a
whole-number line were marked LOSS instead of PUSH."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from check_results import resolve_h2h, calculate_pnl, resolve_market_result


class ResolveH2HTests(unittest.TestCase):
    def test_home_pick_wins_when_home_scores_more(self):
        self.assertEqual(resolve_h2h("Warriors", "Warriors", "Storm", 24, 12), "win")

    def test_home_pick_loses_when_away_scores_more(self):
        self.assertEqual(resolve_h2h("Warriors", "Warriors", "Storm", 10, 30), "loss")

    def test_away_pick_wins(self):
        self.assertEqual(resolve_h2h("Storm", "Warriors", "Storm", 10, 30), "win")

    def test_draw_pick_wins_on_draw_and_loses_otherwise(self):
        self.assertEqual(resolve_h2h("Draw", "Spain", "Argentina", 1, 1), "win")
        self.assertEqual(resolve_h2h("Draw", "Spain", "Argentina", 2, 1), "loss")

    def test_team_pick_on_drawn_match_is_a_loss(self):
        # backed a side, game drew -> H2H two-way loses (three-way market)
        self.assertEqual(resolve_h2h("Spain", "Spain", "Argentina", 1, 1), "loss")

    def test_partial_name_matches_ledger_style(self):
        # ledger picks are often uppercase/partial: "NEW ZEALAND WARRIORS"
        self.assertEqual(resolve_h2h("NEW ZEALAND WARRIORS", "New Zealand Warriors",
                                     "St George Illawarra Dragons", 20, 6), "win")

    def test_incomplete_scores_return_none_never_guessed(self):
        self.assertIsNone(resolve_h2h("Warriors", "Warriors", "Storm", None, 12))
        self.assertIsNone(resolve_h2h("Warriors", "Warriors", "Storm", 12, None))


class TotalsSettlingTests(unittest.TestCase):
    """Exercises the totals branch via the same expressions check_and_resolve
    uses — kept as direct expression tests since the branch reads scores from
    the API inside check_and_resolve. The push case is the 2026-07-21 bug."""

    def _settle(self, pick_text, total):
        pick_text = pick_text.lower()
        if 'over' in pick_text:
            line = float(pick_text.split('over')[-1].strip())
            return "win" if total > line else ("push" if total == line else "loss")
        line = float(pick_text.split('under')[-1].strip())
        return "win" if total < line else ("push" if total == line else "loss")

    def test_under_wins_below_the_line(self):
        self.assertEqual(self._settle("UNDER 7", 5), "win")

    def test_under_loses_above_the_line(self):
        self.assertEqual(self._settle("UNDER 7", 9), "loss")

    def test_exact_whole_number_line_is_a_push_not_a_loss(self):
        """THE BUG: UNDER 7 with a 4-3 final (total exactly 7) was being
        recorded as a loss. It's a push — stake refunded, no W or L."""
        self.assertEqual(self._settle("UNDER 7", 7), "push")
        self.assertEqual(self._settle("OVER 7", 7), "push")

    def test_half_lines_can_never_push(self):
        self.assertEqual(self._settle("UNDER 49.5", 49), "win")
        self.assertEqual(self._settle("UNDER 49.5", 50), "loss")

    def test_settled_source_matches_production_code(self):
        """Guard against this test drifting from the real implementation:
        the exact fixed expressions must exist in check_results.py."""
        import inspect, check_results
        src = inspect.getsource(check_results)
        self.assertIn('("push" if total == line else "loss")', src)


class ResolveMarketResultTests(unittest.TestCase):
    """resolve_market_result (2026-10-11) — extracted from check_and_resolve
    so my_bets.py (personal flat-stake log) can resolve a bet the same way
    the public ledger does, for both singles and multi legs. Behaviour must
    match check_and_resolve's old inline logic exactly — covered by the
    pre-existing TotalsSettlingTests/ResolveH2HTests above still passing
    unchanged, plus these direct tests of the new entry point."""

    def test_handicap_is_always_manual(self):
        self.assertEqual(
            resolve_market_result("Handicap", "WARRIORS -6.5", "Warriors", "Storm", 24, 12),
            "manual",
        )

    def test_total_delegates_to_the_same_push_fix(self):
        self.assertEqual(
            resolve_market_result("Total", "UNDER 7", "Warriors", "Storm", 4, 3), "push"
        )
        self.assertEqual(
            resolve_market_result("Total", "OVER 42.5", "Warriors", "Storm", 30, 20), "win"
        )

    def test_h2h_delegates_to_resolve_h2h(self):
        self.assertEqual(
            resolve_market_result("Head to Head", "Warriors", "Warriors", "Storm", 24, 12),
            "win",
        )

    def test_incomplete_scores_return_none(self):
        self.assertIsNone(
            resolve_market_result("Head to Head", "Warriors", "Warriors", "Storm", None, 12)
        )

    def test_unparseable_total_text_returns_none(self):
        self.assertIsNone(
            resolve_market_result("Total", "neither direction named", "Warriors", "Storm", 10, 10)
        )


class PnlTests(unittest.TestCase):
    def test_win_pays_odds_minus_stake(self):
        self.assertEqual(calculate_pnl("win", 1.90), 9.0)

    def test_loss_costs_flat_stake(self):
        self.assertEqual(calculate_pnl("loss", 1.90), -10.0)

    def test_push_is_zero(self):
        self.assertEqual(calculate_pnl("push", 1.90), 0.0)


if __name__ == "__main__":
    unittest.main()
