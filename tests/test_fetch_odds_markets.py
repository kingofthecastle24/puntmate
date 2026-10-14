import os, sys, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from fetch_odds import (
    extract_spread_odds, extract_totals_odds, calc_two_way_implied_probs,
    fetch_upcoming_odds, TOTALS_ONLY_SPORTS,
    extract_best_odds, DRAW_POSSIBLE_SPORTS,
)


def _match(bookmakers):
    return {"home_team": "Warriors", "away_team": "Storm", "bookmakers": bookmakers}


class DrawCaptureTests(unittest.TestCase):
    """Regression test for the "Winnipeg Jets or Draw" bug (2026-10-13,
    Micah): a stray 3-way price from one AU bookmaker on an NHL game got
    treated as a real draw, producing a "Double Chance" selection that
    can't exist for a sport where the final result is never a draw.
    extract_best_odds must only capture a Draw price for a sport in
    DRAW_POSSIBLE_SPORTS -- everything else always has a winner."""

    def _match_with_draw_price(self):
        return _match([
            {"markets": [{"key": "h2h", "outcomes": [
                {"name": "Warriors", "price": 1.80},
                {"name": "Storm", "price": 2.20},
                {"name": "Draw", "price": 15.0},
            ]}]},
        ])

    def test_draw_is_captured_for_a_sport_that_can_really_draw(self):
        for sport in DRAW_POSSIBLE_SPORTS:
            result = extract_best_odds(self._match_with_draw_price(), sport)
            self.assertEqual(result["draw"], 15.0, msg=f"sport={sport}")

    def test_draw_is_never_captured_for_nhl_even_if_a_bookmaker_quotes_one(self):
        result = extract_best_odds(self._match_with_draw_price(), "icehockey_nhl")
        self.assertIsNone(result["draw"])
        self.assertEqual(result["home"], 1.80)
        self.assertEqual(result["away"], 2.20)

    def test_draw_is_never_captured_for_other_always_has_a_winner_sports(self):
        for sport in ("basketball_nba", "baseball_mlb", "tennis_atp_wimbledon",
                      "mma_mixed_martial_arts", "boxing_boxing"):
            result = extract_best_odds(self._match_with_draw_price(), sport)
            self.assertIsNone(result["draw"], msg=f"sport={sport}")


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


class SportLabelSyncTests(unittest.TestCase):
    """Regression test for the 2026-07-18 weekend-multi dry run: fetch_odds.py
    and generate_pick.py each keep their own SPORT_LABELS dict, and
    "rugbyunion_international" was added to fetch_odds.SPORTS (commit
    63fb7e4) without updating generate_pick.py's copy. That gap meant a real
    pick on a Test match would show the raw API sport key
    ("rugbyunion_international") instead of a readable label in the actual
    Telegram/Instagram copy. This asserts every sport fetch_odds.py can
    return has a real label in BOTH dicts, so the two can't drift apart
    again unnoticed."""

    def test_every_fetchable_sport_has_a_label_in_both_modules(self):
        import fetch_odds
        import generate_pick

        for sport in fetch_odds.SPORTS:
            self.assertIn(sport, fetch_odds.SPORT_LABELS,
                          f"{sport} is fetched but has no fetch_odds.SPORT_LABELS entry")
            self.assertIn(sport, generate_pick.SPORT_LABELS,
                          f"{sport} is fetched but has no generate_pick.SPORT_LABELS entry "
                          f"— a real pick on this sport would show the raw API key in public copy")

    def test_priority_sports_match_between_fetch_odds_and_generate_pick(self):
        """fetch_odds.py and generate_pick.py each keep their own
        PRIORITY_SPORTS set (one drives fetch ordering + the final sort,
        the other drives featured-pick selection) -- they must name exactly
        the same sports or the two stages of "prioritise NRL/Rugby/MMA/
        World Cup" would silently disagree with each other."""
        import fetch_odds
        import generate_pick
        self.assertEqual(fetch_odds.PRIORITY_SPORTS, generate_pick.PRIORITY_SPORTS)


class PrioritySportOrderingTests(unittest.TestCase):
    """2026-07-18 (Micah): cater to a NZ/Australian audience -- prioritise
    the FIFA World Cup, NRL, both rugby codes, and MMA over everything
    else. fetch_upcoming_odds() previously sorted the final list by
    kickoff time ALONE, which silently undid SPORTS being priority-ordered:
    a same-day fallback-sport match (e.g. MLB) kicking off earlier than a
    priority-sport match (e.g. NRL) would bump the NRL match out of
    generate_pick.MAX_MATCHES_IN_PROMPT and main.py's NO_BET watchlist
    top-5, even though NRL should never lose that spot to MLB."""

    def _mock_match(self, home, away, kickoff, sport_price=1.80):
        return [{
            "commence_time": kickoff,
            "home_team": home,
            "away_team": away,
            "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
                {"name": home, "price": sport_price},
                {"name": away, "price": 2.10},
            ]}]}],
        }]

    def test_priority_sport_sorted_ahead_of_earlier_fallback_sport_match(self):
        import fetch_odds
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        earlier = (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        later = (now + timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def fake_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            if "baseball_mlb" in url:
                resp.json.return_value = self._mock_match("Yankees", "Red Sox", earlier)
            elif "rugbyleague_nrl" in url:
                resp.json.return_value = self._mock_match("Warriors", "Storm", later)
            else:
                resp.json.return_value = []
            resp.raise_for_status = lambda: None
            return resp

        with patch.object(fetch_odds.requests, "get", side_effect=fake_get):
            matches = fetch_odds.fetch_upcoming_odds()

        sports_in_order = [m["sport"] for m in matches]
        # NRL match kicks off LATER than the MLB match but must still sort first.
        self.assertLess(sports_in_order.index("rugbyleague_nrl"), sports_in_order.index("baseball_mlb"))

    def test_hours_ahead_widens_the_lookahead_window(self):
        """2026-07-19 (Micah): the weekend multi job needs a wider net than
        the ordinary daily 24h window to pool Fri/Sat/Sun fixtures into one
        combined build -- hours_ahead makes that a one-line call, reusing
        every bit of extraction/sort/priority logic unchanged."""
        import fetch_odds
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        in_30h = (now + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def fake_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            if "rugbyleague_nrl" in url:
                resp.json.return_value = self._mock_match("Warriors", "Storm", in_30h)
            else:
                resp.json.return_value = []
            resp.raise_for_status = lambda: None
            return resp

        with patch.object(fetch_odds.requests, "get", side_effect=fake_get):
            matches_default = fetch_odds.fetch_upcoming_odds()
            matches_wide = fetch_odds.fetch_upcoming_odds(hours_ahead=76)

        self.assertEqual(len(matches_default), 0)  # 30h away -> outside the default 24h window
        self.assertEqual(len(matches_wide), 1)      # -> inside a 76h weekend window


class MmaTotalsOnlyTests(unittest.TestCase):
    """2026-10-13 (Micah): wants round/totals markets for UFC. MMA has no
    handicap market, so it gets its own TOTALS_ONLY_SPORTS set rather than
    joining EXPANDED_MARKET_SPORTS (which also requests+extracts spreads)."""

    def test_mma_is_totals_only_not_expanded(self):
        import fetch_odds
        self.assertIn("mma_mixed_martial_arts", TOTALS_ONLY_SPORTS)
        self.assertNotIn("mma_mixed_martial_arts", fetch_odds.EXPANDED_MARKET_SPORTS)

    def test_mma_request_asks_for_totals_but_not_spreads(self):
        import fetch_odds
        now = datetime.now(timezone.utc)
        kickoff = (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        seen_params = {}

        def fake_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            if "mma_mixed_martial_arts" in url:
                seen_params["markets"] = params["markets"]
                resp.json.return_value = [{
                    "commence_time": kickoff,
                    "home_team": "Foster",
                    "away_team": "Asher",
                    "bookmakers": [{"markets": [
                        {"key": "h2h", "outcomes": [
                            {"name": "Foster", "price": 1.80},
                            {"name": "Asher", "price": 2.10},
                        ]},
                        {"key": "totals", "outcomes": [
                            {"name": "Over", "point": 2.5, "price": 1.90},
                            {"name": "Under", "point": 2.5, "price": 1.90},
                        ]},
                    ]}],
                }]
            else:
                resp.json.return_value = []
            resp.raise_for_status = lambda: None
            return resp

        with patch.object(fetch_odds.requests, "get", side_effect=fake_get):
            matches = fetch_odds.fetch_upcoming_odds()

        self.assertEqual(seen_params["markets"], "h2h,totals")
        mma = next(m for m in matches if m["sport"] == "mma_mixed_martial_arts")
        self.assertEqual(mma["markets_extra"]["totals"]["over"]["point"], 2.5)
        self.assertNotIn("spreads", mma["markets_extra"])

    def test_mma_fight_with_no_totals_quoted_has_no_markets_extra(self):
        """Confirms the realistic, common case (per the live check, 2026-10-13:
        a real 41-fight card had zero bookmakers quoting totals on the fight
        checked) doesn't break anything -- it's just absent, same as today."""
        import fetch_odds
        now = datetime.now(timezone.utc)
        kickoff = (now + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")

        def fake_get(url, params=None, timeout=None):
            resp = MagicMock()
            resp.status_code = 200
            resp.headers = {}
            if "mma_mixed_martial_arts" in url:
                resp.json.return_value = [{
                    "commence_time": kickoff,
                    "home_team": "Foster",
                    "away_team": "Asher",
                    "bookmakers": [{"markets": [{"key": "h2h", "outcomes": [
                        {"name": "Foster", "price": 1.80},
                        {"name": "Asher", "price": 2.10},
                    ]}]}],
                }]
            else:
                resp.json.return_value = []
            resp.raise_for_status = lambda: None
            return resp

        with patch.object(fetch_odds.requests, "get", side_effect=fake_get):
            matches = fetch_odds.fetch_upcoming_odds()

        mma = next(m for m in matches if m["sport"] == "mma_mixed_martial_arts")
        self.assertEqual(mma["markets_extra"], {})


if __name__ == "__main__":
    unittest.main()
