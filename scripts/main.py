"""
main.py — PuntMate NZ daily picks pipeline
Runs via GitHub Actions on schedule

Flow: Fetch odds → Generate picks (3 personalities) → Post to Telegram + Facebook → Save latest_run.json
"""

import sys
import os
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fetch_odds import fetch_upcoming_odds
from generate_pick import generate_picks_for_matches
from post_telegram import post_daily_header, post_all_picks, post_no_picks, send_picks_card

# Facebook posting is optional — only runs if secrets are set
FB_ENABLED = bool(os.environ.get('FACEBOOK_PAGE_TOKEN') and os.environ.get('FACEBOOK_PAGE_ID'))
if FB_ENABLED:
    from post_facebook import (
        post_daily_header as fb_post_header,
        post_all_picks as fb_post_picks,
        post_no_picks as fb_post_no_picks,
    )

# Instagram posting is optional — requires image + token
IG_ENABLED = bool(os.environ.get('INSTAGRAM_ACCESS_TOKEN') and os.environ.get('INSTAGRAM_USER_ID'))
if IG_ENABLED:
    from generate_picks_image import generate_picks_image
    from post_instagram import post_picks_to_instagram

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

    # 3. Post to Telegram + Facebook grouped by personality
    match_count = len(matches)
    print(f"\n[3/4] Posting picks ({match_count} match(es), 3 personality blocks)...")

    print("  → Telegram")
    post_daily_header(len(picks))
    post_all_picks(picks)

    if FB_ENABLED:
        print("  → Facebook")
        fb_post_header(len(picks))
        fb_post_picks(picks)
    else:
        print("  → Facebook (skipped — FACEBOOK_PAGE_TOKEN not set)")

    # 3b. Generate picks card + carousel slides
    print("\n  → Generating picks card + carousel...")
    card_dir       = os.path.join(REPO_ROOT, 'data', 'cards')
    card_paths     = []
    carousel_paths = []
    date_str = datetime.now(timezone.utc).strftime('%-d %B %Y')

    try:
        from generate_picks_image import generate_picks_images
        card_paths = generate_picks_images(picks, output_dir=card_dir, date_str=date_str)
        print(f"  Summary card: {len(card_paths)} file(s)")
    except Exception as e:
        print(f"  ⚠️  Summary card failed: {e}")

    try:
        from generate_carousel import generate_carousel_slides
        carousel_paths = generate_carousel_slides(picks, output_dir=card_dir, date_str=date_str)
        print(f"  Carousel: {len(carousel_paths)} slide(s)")
    except Exception as e:
        print(f"  ⚠️  Carousel failed: {e}")

    # Send summary card to Telegram
    if card_paths:
        send_picks_card(card_paths[0],
            caption=f"🎯 *PUNTMATE NZ* — {date_str}\nThree picks · Three personalities · #PuntMateNZ")

    # Post to Instagram (carousel preferred, single card fallback)
    if IG_ENABLED:
        print("  → Instagram")
        if carousel_paths:
            from post_instagram import post_carousel_to_instagram
            post_carousel_to_instagram(picks, carousel_paths)
        elif card_paths:
            from post_instagram import post_picks_to_instagram
            post_picks_to_instagram(picks, card_paths[0])
    else:
        print("  → Instagram (skipped — INSTAGRAM_ACCESS_TOKEN not set)")

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
