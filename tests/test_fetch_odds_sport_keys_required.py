"""
Tests for the 2026-10-15 redesign's fetch_odds.fetch_upcoming_odds
signature change: sport_keys is now required and an empty list makes
zero HTTP requests. Run #206 burned the account's entire monthly
allowance by always scanning the full 14-sport registry -- this is the
change that makes a bounded, Stage-1-selected scan possible at all.
"""
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import fetch_odds


class EmptySportKeysTests(unittest.TestCase):
    @patch("fetch_odds.requests.get")
    def test_empty_sport_keys_makes_zero_requests(self, mock_get):
        matches = fetch_odds.fetch_upcoming_odds([])
        self.assertEqual(matches, [])
        mock_get.assert_not_called()

    @patch("fetch_odds.requests.get")
    def test_only_the_named_sports_are_queried(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        resp.headers = {}
        mock_get.return_value = resp

        fetch_odds.fetch_upcoming_odds(["rugbyleague_nrl", "mma_mixed_martial_arts"])

        queried = [c.args[0] for c in mock_get.call_args_list]
        self.assertEqual(len(queried), 2)
        self.assertTrue(any("rugbyleague_nrl" in u for u in queried))
        self.assertTrue(any("mma_mixed_martial_arts" in u for u in queried))
        self.assertFalse(any("soccer_fifa_world_cup" in u for u in queried))

    def test_sport_keys_is_a_required_positional_argument(self):
        with self.assertRaises(TypeError):
            fetch_odds.fetch_upcoming_odds()


class SportCreditCostTests(unittest.TestCase):
    def test_expanded_market_sport_costs_three(self):
        self.assertEqual(fetch_odds.sport_credit_cost("rugbyleague_nrl"), 3)

    def test_totals_only_sport_costs_two(self):
        self.assertEqual(fetch_odds.sport_credit_cost("mma_mixed_martial_arts"), 2)

    def test_h2h_only_sport_costs_one(self):
        self.assertEqual(fetch_odds.sport_credit_cost("icehockey_nhl"), 1)


if __name__ == "__main__":
    unittest.main()
