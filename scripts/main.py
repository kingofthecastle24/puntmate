"""
main.py — PuntMate NZ daily picks pipeline
Runs via GitHub Actions on schedule

Flow: Fetch odds → Generate picks (3 personalities) → Post to Telegram → Save latest_run.json
"""

import sys
import os
import json
from datetime import datetime, timezone
from fetch_odds import fetch_upcoming_odds
from generate_pick import generate_picks_for_matches
from post_telegram import post_daily_header, post_all_picks, post_no_picks

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')


def save_latest_run(matches, picks):
    """
    Write data/latest_run.json with enriched pick data for log_picks.py.
    Merges pick output with raw match data (sport_key, home_team, away_team).
    """
    match_lookup = {m['match']: m for m in matches}

    enriched_picks = []
    for pick in picks:
        raw = match_lookup.get(pick.get('match'), {})
        enriched_picks.append({
            **pick,
            "sport_key": raw.get('sport', ''),
            "home_team": raw.get('home_team', pick.get('home_team', '')),
            "away_team": raw.get('away_team', pick.get('away_team', '')),
        })

    run_data = {
        "run_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "picks": enriched_picks,
    }

    os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
    with open(LATEST_RUN_PATH, 'w') as f:
        json.dump(run_data, f, indent=2)
    print(f"  Saved {len(enriched_picks)} picks to data/latest_run.json")


def run():
    print("=" * 50)
    print("PuntMate NZ — Daily Picks Pipeline")
    print("=" * 50)

    # 1. Fetch odds
    print("\n[1/4] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()
    print(f"Found {len(matches)} matches in next 48hrs")

    if not matches:
        print("No upcoming matches found — posting no-picks message")
        post_no_picks()
        return

    # 2. Generate picks (3 personalities per match)
    print(f"\n[2/4] Generating Investor/Punter/Gambler picks for {len(matches)} matches...")
    picks = generate_picks_for_matches(matches)
    print(f"\nGenerated {len(picks)} picks total")

    if not picks:
        print("No picks generated — posting no-picks message")
        post_no_picks()
        return

    # 3. Post to Telegram grouped by personality
    match_count = len(matches)
    print(f"\n[3/4] Posting to Telegram ({match_count} match(es), 3 personality blocks)...")
    post_daily_header(len(picks))
    post_all_picks(picks)

    # 4. Save latest run for results tracking
    print("\n[4/4] Saving run data for results tracker...")
    save_latest_run(matches, picks)

    print("\n✅ Done — all picks posted to PuntMate NZ Telegram")
    print("=" * 50)


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    run()
