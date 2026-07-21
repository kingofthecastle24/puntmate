"""
check_results.py — Resolves pending picks against completed scores.
Run via check_results.yml workflow at 11pm NZT (11am UTC) daily.
Uses The Odds API /scores endpoint (free tier, no extra quota cost).

Flat stake: $10 NZD per pick.
"""

import json
import os
import requests
from datetime import datetime, timezone

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4"

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')
FLAT_STAKE = 10.0  # NZD


def fetch_scores(sport_key, days_from=3):
    """Fetch completed scores for a sport. Returns list of score objects."""
    url = f"{BASE_URL}/sports/{sport_key}/scores"
    params = {
        "apiKey": ODDS_API_KEY,
        "daysFrom": days_from,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  Error fetching scores for {sport_key}: {e}")
        return []


def resolve_h2h(pick_name, home_team, away_team, home_score, away_score):
    """Resolve a head-to-head or draw pick. Returns 'win', 'loss', or 'push'."""
    if home_score is None or away_score is None:
        return None  # incomplete

    home_score = float(home_score)
    away_score = float(away_score)

    if home_score > away_score:
        winner = home_team
    elif away_score > home_score:
        winner = away_team
    else:
        winner = "Draw"

    pick_lower = pick_name.lower()
    winner_lower = winner.lower()

    if pick_lower == "draw":
        return "win" if winner == "Draw" else "loss"
    elif pick_lower in home_team.lower() or home_team.lower() in pick_lower:
        return "win" if winner_lower in home_team.lower() else "loss"
    elif pick_lower in away_team.lower() or away_team.lower() in pick_lower:
        return "win" if winner_lower in away_team.lower() else "loss"
    else:
        # Fuzzy fallback: check if pick name appears in winner
        if pick_lower in winner_lower or winner_lower in pick_lower:
            return "win"
        return "loss"


def calculate_pnl(result, odds):
    """Calculate P&L for a $10 flat stake."""
    if result == "win":
        return round(FLAT_STAKE * (odds - 1), 2)
    elif result == "loss":
        return round(-FLAT_STAKE, 2)
    else:
        return 0.0  # push


def check_and_resolve():
    if not os.path.exists(PICKS_PATH):
        print("No picks.json found — nothing to resolve")
        return 0

    with open(PICKS_PATH, 'r') as f:
        all_picks = json.load(f)

    pending = [p for p in all_picks if p['result'] == 'pending']
    if not pending:
        print("No pending picks to resolve")
        return 0

    print(f"Found {len(pending)} pending pick(s) to resolve...")

    # Group pending picks by sport_key to minimise API calls
    by_sport = {}
    for pick in pending:
        sk = pick['sport_key']
        by_sport.setdefault(sk, []).append(pick)

    resolved_count = 0

    for sport_key, sport_picks in by_sport.items():
        scores = fetch_scores(sport_key)
        if not scores:
            print(f"  [{sport_key}] No scores returned")
            continue

        # Build a lookup: (home_team, away_team) → score data
        score_map = {}
        for game in scores:
            if not game.get('completed'):
                continue
            key = (game['home_team'], game['away_team'])
            scores_list = game.get('scores') or []
            score_by_team = {s['name']: s['score'] for s in scores_list}
            score_map[key] = {
                'home_score': score_by_team.get(game['home_team']),
                'away_score': score_by_team.get(game['away_team']),
            }

        for pick in sport_picks:
            match_key = (pick['home_team'], pick['away_team'])
            if match_key not in score_map:
                print(f"  [{sport_key}] No completed score yet: {pick['match']}")
                continue

            score_data = score_map[match_key]
            market = pick.get('market', 'Head to Head')

            if 'handicap' in market.lower():
                # Can't auto-resolve handicap without knowing the line
                result = "manual"
                pnl = None
            elif 'total' in market.lower():
                # Over/Under: pick name contains "Over X.5" or "Under X.5"
                pick_text = pick['pick'].lower()
                home_s = float(score_data['home_score'] or 0)
                away_s = float(score_data['away_score'] or 0)
                total = home_s + away_s
                # BUG FIX (2026-07-21, found in coverage review): a total
                # landing EXACTLY on a whole-number line (e.g. UNDER 7 with
                # a 4-3 final) is a PUSH — stake refunded — not a loss.
                # This mattered immediately: real picks on the ledger use
                # whole-number lines ("UNDER 7"). Miscounting pushes as
                # losses corrupts the public strike rate.
                if 'over' in pick_text:
                    line = float(pick_text.split('over')[-1].strip())
                    result = "win" if total > line else ("push" if total == line else "loss")
                elif 'under' in pick_text:
                    line = float(pick_text.split('under')[-1].strip())
                    result = "win" if total < line else ("push" if total == line else "loss")
                else:
                    result = None
                pnl = calculate_pnl(result, pick['odds']) if result else None
            else:
                # Default: H2H
                result = resolve_h2h(
                    pick['pick'],
                    pick['home_team'],
                    pick['away_team'],
                    score_data['home_score'],
                    score_data['away_score']
                )
                pnl = calculate_pnl(result, pick['odds']) if result else None

            if result:
                # Update in all_picks
                for p in all_picks:
                    if p['id'] == pick['id']:
                        p['result'] = result
                        p['pnl'] = pnl
                        break
                resolved_count += 1
                pnl_str = f"${pnl:+.2f}" if pnl is not None else "manual"
                print(f"  ✅ {pick['match']}: {result.upper()} ({pnl_str})")

    # Save updated picks
    with open(PICKS_PATH, 'w') as f:
        json.dump(all_picks, f, indent=2)

    print(f"\n✅ Resolved {resolved_count} pick(s)")
    return resolved_count


if __name__ == "__main__":
    resolved = check_and_resolve()

    # Print summary stats
    if os.path.exists(PICKS_PATH):
        with open(PICKS_PATH, 'r') as f:
            all_picks = json.load(f)
        settled = [p for p in all_picks if p['result'] not in ('pending', 'manual', None)]
        wins = sum(1 for p in settled if p['result'] == 'win')
        losses = sum(1 for p in settled if p['result'] == 'loss')
        total_pnl = sum(p['pnl'] for p in settled if p['pnl'] is not None)
        print(f"\nAll-time: {wins}W / {losses}L | P&L: ${total_pnl:+.2f}")
