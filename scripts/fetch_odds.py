"""
fetch_odds.py — Pulls upcoming match odds via The Odds API (free tier)
Covers: FIFA World Cup 2026, NRL, Super Rugby Pacific, UFC/MMA, Wimbledon
Free tier: 500 requests/month — uses ~2-3/day

Sign up for a free key at: https://the-odds-api.com
Set ODDS_API_KEY in GitHub Secrets.
"""

import os
import requests
import json
from datetime import datetime, timezone

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4"

# Sports to pull — priority order (most popular NZ viewing first)
SPORTS = [
    "soccer_fifa_world_cup",            # FIFA World Cup 2026 (live now)
    "rugbyleague_nrl",                  # NRL — core NZ audience
    "rugbyunion_super_rugby",           # Super Rugby Pacific
    "mma_mixed_martial_arts",           # UFC/MMA
    "tennis_atp_wimbledon",             # Wimbledon ATP (July)
    "tennis_wta_wimbledon",             # Wimbledon WTA (July)
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
}

# Events that warrant the Matchday Print (cream/red) look instead of Betslip Night
BIG_GAME_SPORTS = {"soccer_fifa_world_cup", "mma_mixed_martial_arts"}
BIG_GAME_KEYWORDS = ["All Blacks", "Wallabies", "Warriors", "Final", "Semi-Final",
                     "Quarter-Final", "Grand Final", "Championship", "World Cup Final"]


def fetch_upcoming_odds():
    """Fetch odds for all configured sports. Returns list of match dicts."""
    all_matches = []

    for sport in SPORTS:
        try:
            url = f"{BASE_URL}/sports/{sport}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "au",        # Australian/NZ bookmakers (includes TAB)
                "markets": "h2h",
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
                if 0 < hours_away < 48:  # TEMP: widened from 24h for one test run, see commit msg
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
    """Line-shop across all bookmakers to find the best available price."""
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


if __name__ == "__main__":
    matches = fetch_upcoming_odds()
    print(json.dumps(matches, indent=2))
