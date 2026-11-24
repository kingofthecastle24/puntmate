import os, sys, unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fetch_odds


def _resp(status, payload):
    r = MagicMock(); r.status_code = status; r.json.return_value = payload; r.text = ""
    r.raise_for_status.return_value = None
    return r


class ActiveSportsSkipTests(unittest.TestCase):
    def test_out_of_season_sports_are_not_fetched(self):
        called = []
        def fake_get(url, params=None, timeout=None):
            called.append(url)
            if url.endswith("/sports"):
                return _resp(200, [{"key": "basketball_nba", "active": True},
                                   {"key": "tennis_atp_wimbledon", "active": False}])
            return _resp(200, [])
        with patch.object(fetch_odds.requests, "get", side_effect=fake_get):
            fetch_odds.fetch_upcoming_odds()
        odds_calls = [u for u in called if u.endswith("/odds")]
        self.assertEqual(odds_calls, [f"{fetch_odds.BASE_URL}/sports/basketball_nba/odds"])

    def test_sports_list_failure_falls_back_to_all(self):
        def fake_get(url, params=None, timeout=None):
            if url.endswith("/sports"):
                return _resp(401, {})
            return _resp(200, [])
        with patch.object(fetch_odds.requests, "get", side_effect=fake_get) as g:
            fetch_odds.fetch_upcoming_odds()
        self.assertEqual(g.call_count, 1 + len(fetch_odds.SPORTS))


if __name__ == "__main__":
    unittest.main()
