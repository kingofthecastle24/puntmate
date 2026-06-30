"""
main.py — PuntMate NZ daily picks pipeline
Runs via GitHub Actions on schedule

Flow: Fetch odds → Generate picks via Claude → Post to Telegram
"""

import sys
import os
from fetch_odds import fetch_upcoming_odds
from generate_pick import generate_picks_for_matches
from post_telegram import post_daily_header, post_pick, post_no_picks

def run():
    print("=" * 50)
    print("PuntMate NZ — Daily Picks Pipeline")
    print("=" * 50)

    # 1. Fetch odds
    print("\n[1/3] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()
    print(f"Found {len(matches)} matches in next 48hrs")

    if not matches:
        print("No upcoming matches found — posting no-picks message")
        post_no_picks()
        return

    # 2. Generate picks
    print(f"\n[2/3] Generating picks for {len(matches)} matches...")
    picks = generate_picks_for_matches(matches)
    print(f"Generated {len(picks)} picks")

    if not picks:
        print("No picks generated — posting no-picks message")
        post_no_picks()
        return

    # 3. Post to Telegram
    print(f"\n[3/3] Posting {len(picks)} picks to Telegram...")
    post_daily_header(len(picks))

    for pick in picks:
        post_pick(pick)

    print("\n✅ Done — all picks posted to PuntMate NZ Telegram")
    print("=" * 50)


if __name__ == "__main__":
    # Validate required env vars
    required = ['ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)

    run()
