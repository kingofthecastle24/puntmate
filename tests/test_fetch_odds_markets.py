import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fetch_odds import extract_spread_odds, extract_totals_odds, calc_two_way_implied_probs


def _match(bookmakers):
    return {"home_team": "Warriors", "away_team": "Storm", "bookmakers": bookmakers}


class SpreadOddsTests(unittest.TestCase):
    def test_picks_best_price_at_the_anchor_line(self):
        match = _match([
            {"markets": [{"key": "spreads", "outcomes": [
                {"name": "Warriors", "point": -6.5, "price": 1.90},
                {"name": "Storm", "point": 6.5, "price": 1.90},
            ]}]},
            {"markets": [{"key": "spreads", "outcomes": [
                {"name": "Warriors", "point": -6.5, "price": 1.95},  # better price, same line
                {"name": "Storm", "point": 6.5, "price": 1.85},
            ]}]},
        ])
        result = extract_spread_odds(match)
        self.assertEqual(result["home"]["price"], 1.95)
        self.assertEqual(result["home"]["point"], -6.5)

    def test_ignores_different_line_from_a_second_bookmaker(self):
        match = _match([
            {"markets": [{"key": "spreads", "outcomes": [
                {"name": "Warriors", "point": -6.5, "price": 1.90},
                {"name": "Storm", "point": 6.5, "price": 1.90},
            ]}]},
            {"markets": [{"key": "spreads", "outcomes": [
                {"name": "Warriors", "point": -9.5, "price": 2.50},  # different line — must be skipped
                {"name": "Storm", "point": 9.5, "price": 1.50},
            ]}]},
        ])
        result = extract_spread_odds(match)
        self.assertEqual(result["home"]["point"], -6.5)
        self.assertEqual(result["home"]["price"], 1.90)  # not 2.50 from the mismatched line

    def test_no_spreads_market_returns_none(self):
        match = _match([{"markets": [{"key": "h2h", "outcomes": [
            {"name": "Warriors", "price": 1.80}, {"name": "Storm", "price": 2.05},
        ]}]}])
        self.assertIsNone(extract_spread_odds(match))


class TotalsOddsTests(unittest.TestCase):
    def test_picks_best_price_at_anchor_line(self):
        match = _match([
            {"markets": [{"key": "totals", "outcomes": [
                {"name": "Over", "point": 42.5, "price": 1.90},
                {"name": "Under", "point": 42.5, "price": 1.90},
            ]}]},
            {"markets": [{"key": "totals", "outcomes": [
                {"name": "Over", "point": 42.5, "price": 2.00},
                {"name": "Under", "point": 42.5, "price": 1.80},
            ]}]},
        ])
        result = extract_totals_odds(match)
        self.assertEqual(result["over"]["price"], 2.00)
        self.assertEqual(result["under"]["price"], 1.90)

    def test_different_total_line_ignored(self):
        match = _match([
            {"markets": [{"key": "totals", "outcomes": [
                {"name": "Over", "point": 42.5, "price": 1.90},
                {"name": "Under", "point": 42.5, "price": 1.90},
            ]}]},
            {"markets": [{"key": "totals", "outcomes": [
                {"name": "Over", "point": 38.5, "price": 2.60},
                {"name": "Under", "point": 38.5, "price": 1.45},
            ]}]},
        ])
        result = extract_totals_odds(match)
        self.assertEqual(result["over"]["point"], 42.5)
        self.assertEqual(result["over"]["price"], 1.90)


class ImpliedProbTests(unittest.TestCase):
    def test_two_way_implied_probs_sum_to_one(self):
        probs = calc_two_way_implied_probs(1.90, 1.90)
        self.assertAlmostEqual(probs["a"] + probs["b"], 1.0, places=4)
        self.assertAlmostEqual(probs["a"], 0.5, places=2)


if __name__ == "__main__":
    unittest.main()
