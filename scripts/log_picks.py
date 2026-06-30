"""
log_picks.py — Logs today's picks to data/picks.json immediately after generation.
Run after main.py. Reads data/latest_run.json (written by main.py) and appends
each pick with result: "pending" for later resolution by check_results.py.
"""

import json
import os
from datetime import datetime, timezone

# Paths relative to repo root
REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')


def log_picks():
    # Load today's run
    if not os.path.exists(LATEST_RUN_PATH):
        print("No latest_run.json found — skipping log")
        return 0

    with open(LATEST_RUN_PATH, 'r') as f:
        run_data = json.load(f)

    picks_to_log = run_data.get('picks', [])
    if not picks_to_log:
        print("No picks in latest_run.json — nothing to log")
        return 0

    # Load existing picks ledger
    if os.path.exists(PICKS_PATH):
        with open(PICKS_PATH, 'r') as f:
            all_picks = json.load(f)
    else:
        all_picks = []

    # Append new picks with pending status
    run_date = run_data.get('run_date', datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    added = 0
    for pick in picks_to_log:
        personality = pick.get('personality', 'punter')
        entry = {
            "id": f"{run_date}_{pick['sport_key']}_{pick['home_team'].replace(' ', '_')}_{personality}",
            "date": run_date,
            "personality": personality,
            "sport_key": pick['sport_key'],
            "sport": pick['sport'],
            "match": pick['match'],
            "home_team": pick['home_team'],
            "away_team": pick['away_team'],
            "pick": pick['pick'],
            "market": pick['market'],
            "odds": float(pick['odds']),
            "confidence": pick['confidence'],
            "result": "pending",
            "pnl": None
        }
        # Avoid duplicates (re-run protection)
        if not any(p['id'] == entry['id'] for p in all_picks):
            all_picks.append(entry)
            added += 1
            print(f"  Logged: {entry['match']} → {entry['pick']} @ {entry['odds']}")
        else:
            print(f"  Skip (already logged): {entry['match']}")

    # Save updated ledger
    with open(PICKS_PATH, 'w') as f:
        json.dump(all_picks, f, indent=2)

    print(f"\n✅ Logged {added} new pick(s) to data/picks.json (total: {len(all_picks)})")
    return added


if __name__ == "__main__":
    log_picks()
