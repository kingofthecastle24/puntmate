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

    # Schema note: latest_run.json now holds ONE pick under "pick" (the
    # single-official-pick model replacing the old investor/punter/gambler
    # personalities), not a "picks" list. Still supports the legacy "picks"
    # list shape for any old fixture/backup files.
    single = run_data.get('pick')
    if single and single.get('has_pick'):
        picks_to_log = [single]
    else:
        picks_to_log = [p for p in run_data.get('picks', []) if p]
    if not picks_to_log:
        print("No pick in latest_run.json (NO_BET or none) — nothing to log")
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
        bet_type = pick.get('bet_type', pick.get('personality', 'PUNTER_BET'))
        sport_key = pick.get('sport_key') or pick.get('sport', '')
        selection = pick.get('selection', pick.get('pick', ''))
        entry = {
            "id": f"{run_date}_{sport_key}_{pick['home_team'].replace(' ', '_')}_{bet_type}",
            "date": run_date,
            "bet_type": bet_type,
            "risk": pick.get('risk', ''),
            "sport_key": sport_key,
            "sport": pick.get('sport', sport_key),
            "match": pick['match'],
            "home_team": pick['home_team'],
            "away_team": pick['away_team'],
            "pick": selection,
            "market": pick['market'],
            "odds": float(pick['odds']),
            "confidence": pick.get('confidence', pick.get('confidence_label', '')),
            "result": "pending",
            "pnl": None
        }
        # Avoid duplicates (re-run protection)
        if not any(p['id'] == entry['id'] for p in all_picks):
            all_picks.append(entry)
            added += 1
            print(f"  Logged: {entry['match']} \u2192 {entry['pick']} @ {entry['odds']}")
        else:
            print(f"  Skip (already logged): {entry['match']}")

    # Save updated ledger
    with open(PICKS_PATH, 'w') as f:
        json.dump(all_picks, f, indent=2)

    print(f"\n✅ Logged {added} new pick(s) to data/picks.json (total: {len(all_picks)})")
    return added


if __name__ == "__main__":
    log_picks()
