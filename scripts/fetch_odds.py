"""
fetch_odds.py — Pulls upcoming match odds via The Odds API (free tier)
Covers: FIFA World Cup 2026, NRL, Super Rugby Pacific, UFC/MMA, Wimbledon
Free tier: 500 requests/month — uses ~2-3/day

Sign up for a free key at: https://the-odds-api.com
Set ODDS_API_KEY in GitHub Secrets.

Markets: head-to-head (moneyline) is fetched for every sport, as before.
For NRL, tennis (ATP/WTA) and football (the FIFA World Cup), spreads
(handicap) and totals (over/under) are ALSO fetched — Phase 1 of the market
widening work: more genuine market surface area per fixture, not a looser
bar for what counts as a real edge (that logic lives in pick_classifier.py
and is untouched).
"""

import os
import requests
import json
from datetime import datetime, timezone

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4"

# Sports to pull — priority order (most popular NZ viewing first).
# Widened 2026-07-18: aim is to cover everything a TAB NZ / Betcha punter can
# actually bet day-to-day, so genuinely empty days (NO_BET with no watchlist)
# become rare. Sports with no fixtures on a given day cost one cheap API call
# and return empty — that's fine. Note: The Odds API is the data source here;
# it can't literally read tab.co.nz/betcha.co.nz, but its AU-region
# bookmakers carry effectively the same fixture set NZ TAB prices up.
SPORTS = [
    "soccer_fifa_world_cup",            # FIFA World Cup 2026 (live now)
    "rugbyleague_nrl",                  # NRL — core NZ audience
    "rugbyunion_super_rugby",           # Super Rugby Pacific
    "mma_mixed_martial_arts",           # UFC/MMA
    "tennis_atp_wimbledon",             # Wimbledon ATP (July)
    "tennis_wta_wimbledon",             # Wimbledon WTA (July)
    "aussierules_afl",                  # AFL — big TAB NZ market
    "baseball_mlb",                     # MLB — daily fixtures, fills quiet days
    "basketball_nba",                   # NBA (off-season now, active Oct-Jun)
    "soccer_epl",                       # Premier League (from Aug)
    "cricket_international_t20",        # International T20s
    "boxing_boxing",                    # Boxing cards
    # July test-window internationals (All Blacks etc). If The Odds API
    # doesn't recognise a key it 4xxs for that sport only — the per-sport
    # try/except logs it and the run continues, so an invalid key is
    # harmless. Check the run log's per-sport lines to confirm coverage.
    "rugbyunion_international",
    "icehockey_nhl",                    # NHL — off-season in July (Oct-Jun), added 2026-07-18
    # for parity with TAB's "US Basketball, NHL and MLB" multi promo category;
    # harmless empty result until the season's back.
]

# Human-readable sport labels for cards
SPORT_LABELS = {
    "soccer_fifa_world_cup":      "WORLD CUP",
    "rugbyleague_nrl":            "NRL",
    "rugbyunion_super_rugby":     "SUPER RUGBY",
    "mma_mixed_martial_arts":     "UFC",
    "tennis_atp_wimbledon":       "WIMBLEDON",
    "tennis_wta_wimbledon":       "WIMBLEDON",
    "tennis_atp_us_open":         "US OPEN",
    "tennis_wta_us_open":         "US OPEN",
    "tennis_atp_australian_open": "AUSTRALIAN OPEN",
    "aussierules_afl":            "AFL",
    "baseball_mlb":               "MLB",
    "basketball_nba":             "NBA",
    "soccer_epl":                 "PREMIER LEAGUE",
    "cricket_international_t20":  "T20 CRICKET",
    "boxing_boxing":              "BOXING",
    "rugbyunion_international":   "TEST RUGBY",
    "icehockey_nhl":              "NHL",
}

# Events that warrant the Matchday Print (cream/red) look instead of Betslip Night
BIG_GAME_SPORTS = {"soccer_fifa_world_cup", "mma_mixed_martial_arts"}
BIG_GAME_KEYWORDS = ["All Blacks", "Wallabies", "Warriors", "Final", "Semi-Final",
                     "Quarter-Final", "Grand Final", "Championship", "World Cup Final"]

# Sports that get spreads (handicap/line) + totals in addition to
# head-to-head. Widened 2026-07-18 to every team sport in SPORTS — handicap
# and totals are core TAB NZ markets and more markets means more chances of
# a genuine edge (the honest route to fewer NO_BET days). MMA/boxing stay
# h2h-only (no meaningful spread market). Note "margin" betting in the NRL
# band sense (e.g. 1-12) isn't offered by The Odds API — handicap (spreads)
# is the closest equivalent and IS covered.
EXPANDED_MARKET_SPORTS = {
    "rugbyleague_nrl",
    "rugbyunion_super_rugby",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
    "soccer_fifa_world_cup",
    "aussierules_afl",
    "baseball_mlb",
    "basketball_nba",
    "soccer_epl",
    "cricket_international_t20",
    "rugbyunion_international",
}


def fetch_upcoming_odds():
    """Fetch odds for all configured sports. Returns list of match dicts."""
    all_matches = []

    for sport in SPORTS:
        try:
            wants_extra_markets = sport in EXPANDED_MARKET_SPORTS
            markets = "h2h,spreads,totals" if wants_extra_markets else "h2h"

            url = f"{BASE_URL}/sports/{sport}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "au",        # Australian/NZ bookmakers (includes TAB)
                "markets": markets,
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            }
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 404:
                print(f"[{sport}] Not in season or no matches (404)")
                continue

            response.raise_for_status()
            matches = response.json()

            now = datetime.now(timezone.utc)
            added = 0

            for match in matches:
                kickoff = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                hours_away = (kickoff - now).total_seconds() / 3600

                # Only today's matches (next 24 hours) for pre-game picks
                if 0 < hours_away < 24:
                    best_odds = extract_best_odds(match)
                    if not best_odds:
                        continue

                    implied = calc_implied_probs(best_odds)
                    sport_label = SPORT_LABELS.get(sport, sport.upper().replace('_', ' '))

                    home = match['home_team']
                    away = match['away_team']
                    is_big_game = (
                        sport in BIG_GAME_SPORTS or
                        any(kw.lower() in (home + ' ' + away).lower()
                            for kw in BIG_GAME_KEYWORDS)
                    )

                    markets_extra = {}
                    if wants_extra_markets:
                        spread = extract_spread_odds(match)
                        if spread:
                            markets_extra["spreads"] = spread
                        total = extract_totals_odds(match)
                        if total:
                            markets_extra["totals"] = total

                    all_matches.append({
                        "sport":              sport,
                        "sport_label":        sport_label,
                        "match":              f"{home} vs {away}",
                        "home_team":          home,
                        "away_team":          away,
                        "kickoff":            match['commence_time'],
                        "hours_until_kick":   round(hours_away, 1),
                        "odds":               best_odds,
                        "implied_probs":      implied,
                        "markets_extra":      markets_extra,   # {} if none available/applicable
                        "big_game":           is_big_game,
                    })
                    added += 1

            quota = response.headers.get('x-requests-remaining', 'unknown')
            print(f"[{sport}] {added} matches today. Quota remaining: {quota}")

        except requests.exceptions.HTTPError as e:
            print(f"[{sport}] HTTP {e.response.status_code}: {e}")
        except Exception as e:
            print(f"[{sport}] Error: {e}")

    all_matches.sort(key=lambda m: m['kickoff'])
    print(f"\nTotal: {len(all_matches)} matches available for today")
    return all_matches


def extract_best_odds(match):
    """Line-shop across all bookmakers to find the best available h2h price."""
    if not match.get('bookmakers'):
        return None

    best = {"home": 0.0, "away": 0.0, "draw": None}
    home, away = match['home_team'], match['away_team']

    for bk in match['bookmakers']:
        for mkt in bk.get('markets', []):
            if mkt['key'] != 'h2h':
                continue
            for outcome in mkt['outcomes']:
                p = outcome['price']
                name = outcome['name']
                if name == home:
                    best['home'] = max(best['home'], p)
                elif name == away:
                    best['away'] = max(best['away'], p)
                elif name.lower() == 'draw':
                    best['draw'] = max(best['draw'] or 0, p) or None

    return best if best['home'] > 0 and best['away'] > 0 else None


def extract_spread_odds(match):
    """
    Line-shop the spreads (handicap) market. Different bookmakers can quote
    different handicap lines (e.g. -6.5 vs -7.5) for the same match — mixing
    the best price from two different lines would be nonsensical, so this
    picks the line the FIRST bookmaker with a spreads market quotes, then
    only line-shops for the best price at that same line across the rest.
    Returns None if no bookmaker offers spreads for this match.
    """
    if not match.get('bookmakers'):
        return None

    home, away = match['home_team'], match['away_team']
    anchor_line = None
    best = {"home": None, "away": None}

    for bk in match['bookmakers']:
        for mkt in bk.get('markets', []):
            if mkt['key'] != 'spreads':
                continue
            for outcome in mkt['outcomes']:
                name = outcome['name']
                point = outcome.get('point')
                price = outcome['price']
                if name not in (home, away) or point is None:
                    continue

                # Anchor to the home team's point on the first sighting —
                # away's point is just the negative of home's for a 2-way
                # spread, so anchoring on one side is enough.
                if anchor_line is None and name == home:
                    anchor_line = point

                if anchor_line is not None:
                    expected_point = anchor_line if name == home else -anchor_line
                    if point != expected_point:
                        continue  # different line at this bookmaker — skip, don't mix

                key = "home" if name == home else "away"
                if best[key] is None or price > best[key]["price"]:
                    best[key] = {"point": point, "price": price}

    if best["home"] and best["away"]:
        return best
    return None


def extract_totals_odds(match):
    """Line-shop the totals (over/under) market — same same-line-only logic
    as extract_spread_odds, anchored on the Over side's point."""
    if not match.get('bookmakers'):
        return None

    anchor_line = None
    best = {"over": None, "under": None}

    for bk in match['bookmakers']:
        for mkt in bk.get('markets', []):
            if mkt['key'] != 'totals':
                continue
            for outcome in mkt['outcomes']:
                name = outcome['name'].lower()
                point = outcome.get('point')
                price = outcome['price']
                if name not in ('over', 'under') or point is None:
                    continue

                if anchor_line is None and name == 'over':
                    anchor_line = point
                if anchor_line is not None and point != anchor_line:
                    continue  # different total line — skip, don't mix

                key = name
                if best[key] is None or price > best[key]["price"]:
                    best[key] = {"point": point, "price": price}

    if best["over"] and best["under"]:
        return best
    return None


def calc_implied_probs(odds):
    """
    Convert decimal odds to implied probabilities, removing the overround
    so values sum to exactly 1.0.
    """
    if not odds:
        return None

    raw = {
        "home": 1 / odds['home'],
        "away": 1 / odds['away'],
    }
    if odds.get('draw') and odds['draw'] > 0:
        raw['draw'] = 1 / odds['draw']

    total = sum(raw.values())
    return {k: round(v / total, 4) for k, v in raw.items()} if total > 0 else None


def calc_two_way_implied_probs(price_a, price_b):
    """Generic 2-outcome implied-probability calc (used for spreads/totals,
    which don't have a draw), overround-adjusted the same way as h2h."""
    if not price_a or not price_b:
        return None
    raw_a, raw_b = 1 / price_a, 1 / price_b
    total = raw_a + raw_b
    if total <= 0:
        return None
    return {"a": round(raw_a / total, 4), "b": round(raw_b / total, 4)}


if __name__ == "__main__":
    matches = fetch_upcoming_odds()
    print(json.dumps(matches, indent=2))
