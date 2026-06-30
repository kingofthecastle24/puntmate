"""
fetch_odds.py — Pulls upcoming match odds via The Odds API (free tier)
Covers: FIFA World Cup, NRL, NBA, Super Rugby
Free tier: 500 requests/month — we use ~2-3/day so well within limit
Sign up for a free key at: https://the-odds-api.com
"""

import os
import requests
import json
from datetime import datetime, timezone

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4"

# Sports to pull — maps to Odds API sport keys
SPORTS = [
    "soccer_fifa_world_cup",   # FIFA World Cup 2026
    "rugbyleague_nrl",         # NRL
    "basketball_nba",          # NBA
    "rugbyunion_super_rugby",  # Rugby
    "tennis_atp_french_open",  # Tennis ATP
    "tennis_wta_french_open",  # Tennis WTA
]

def fetch_upcoming_odds():
    """Fetch odds for all configured sports. Returns list of match dicts."""
    all_matches = []

    for sport in SPORTS:
        try:
            url = f"{BASE_URL}/sports/{sport}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "au",        # Australian/NZ bookmakers
                "markets": "h2h",       # Head to head
                "oddsFormat": "decimal",
                "dateFormat": "iso",
            }
            response = requests.get(url, params=params, timeout=10)

            if response.status_code == 404:
                # Sport not available or no upcoming matches
                continue

            response.raise_for_status()
            matches = response.json()

            # Only take next 48hrs of matches
            now = datetime.now(timezone.utc)
            for match in matches[:3]:  # Top 3 matches per sport
                kickoff = datetime.fromisoformat(match['commence_time'].replace('Z', '+00:00'))
                hours_away = (kickoff - now).total_seconds() / 3600

                if 0 < hours_away < 48:
                    # Find best odds from available bookmakers
                    best_odds = extract_best_odds(match)
                    if best_odds:
                        all_matches.append({
                            "sport": sport,
                            "match": f"{match['home_team']} vs {match['away_team']}",
                            "home_team": match['home_team'],
                            "away_team": match['away_team'],
                            "kickoff": match['commence_time'],
                            "odds": best_odds
                        })

            # Log remaining quota
            quota_remaining = response.headers.get('x-requests-remaining', 'unknown')
            print(f"[{sport}] Found {len(matches)} matches. Quota remaining: {quota_remaining}")

        except Exception as e:
            print(f"[{sport}] Error fetching odds: {e}")
            continue

    return all_matches


def extract_best_odds(match):
    """Extract best available odds from bookmakers."""
    if not match.get('bookmakers'):
        return None

    best = {"home": 0, "away": 0, "draw": None}

    for bookmaker in match['bookmakers']:
        for market in bookmaker.get('markets', []):
            if market['key'] == 'h2h':
                for outcome in market['outcomes']:
                    if outcome['name'] == match['home_team']:
                        best['home'] = max(best['home'], outcome['price'])
                    elif outcome['name'] == match['away_team']:
                        best['away'] = max(best['away'], outcome['price'])
                    elif outcome['name'] == 'Draw':
                        if best['draw'] is None or outcome['price'] > best['draw']:
                            best['draw'] = outcome['price']

    return best if best['home'] > 0 else None


if __name__ == "__main__":
    matches = fetch_upcoming_odds()
    print(json.dumps(matches, indent=2))
