"""
check_results.py — Resolves pending picks against completed scores.
Run via check_results.yml workflow at 11pm NZT (11am UTC) daily.
Uses The Odds API /scores endpoint.

2026-10-15 (redesign, Section 6): this endpoint is NOT free — it costs 2
credits per sport query, the same as any other Odds API call (the old
comment above calling it "free tier, no extra quota cost" was simply
wrong, and rotating through all 14 registered sports with unrestricted
polling could cost 14 x 2 x 31 = 868 credits/month before a single odds
call — more than the account's entire allowance). Distinct sport /scores
calls are now capped at MAX_DAILY_SPORT_SCORE_CALLS per NZ day, reserved
through quota_budget.py's SCORES bucket exactly like Stage 2's odds calls
reserve ODDS credits, and a sport that doesn't make the cap today is
retried tomorrow via a fair urgency ordering (closest to falling out of
the API's 3-day scores history window goes first), not a fixed rotation.

Flat stake: $10 NZD per pick.
"""

import json
import os
import sys
import requests
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
import quota_budget

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')
BASE_URL = "https://api.the-odds-api.com/v4"

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')
FLAT_STAKE = 10.0  # NZD

# The real per-call cost (Section 6: "despite the code comment calling it
# free") and the hard daily cap on distinct sports checked — see the
# module docstring for why both exist.
SCORES_CREDIT_COST = 2
MAX_DAILY_SPORT_SCORE_CALLS = 2

# The Odds API's /scores endpoint only returns completed games from the last
# `daysFrom` days (max 3), so a pick whose match never resolves within that
# window — a team-name mismatch between the odds snapshot and the scores
# response, a sport the scores endpoint doesn't cover well (e.g. individual
# combat-sport fights), or a missed run — falls out of the API's own history
# and can NEVER be auto-resolved again. Previously such a pick just stayed
# "pending" forever with no signal. STALE_PENDING_DAYS bounds how long we
# keep silently retrying before flagging it loudly instead (2026-09-05, found
# via 4 picks stuck pending since as far back as 2026-07-16).
STALE_PENDING_DAYS = 5


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


def _urgency(sport_picks, today):
    """Days until the OLDEST pending pick for this sport falls out of the
    scores endpoint's 3-day history window -- the sport with the highest
    value here is the one that most urgently needs to be checked today."""
    days = []
    for p in sport_picks:
        try:
            days.append((today - date.fromisoformat(p['date'])).days)
        except ValueError:
            days.append(0)
    return max(days) if days else 0


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

    today = datetime.now(timezone.utc).date()

    # Fair rotation, not a fixed order: the sport(s) closest to losing
    # their pending picks out of the 3-day history window go first, so a
    # day that can't afford to check every sport still checks the most
    # urgent ones (Section 6).
    ordered_sports = sorted(by_sport.keys(), key=lambda sk: -_urgency(by_sport[sk], today))

    quota_budget.ensure_current_period()
    period_key = quota_budget.CURRENT_PERIOD_KEY

    resolved_count = 0
    checked_sports = 0
    skipped_sports = []

    for sport_key in ordered_sports:
        sport_picks = by_sport[sport_key]

        if checked_sports >= MAX_DAILY_SPORT_SCORE_CALLS:
            print(f"  [{sport_key}] daily sport-score cap ({MAX_DAILY_SPORT_SCORE_CALLS}) reached — "
                  f"checking tomorrow instead.")
            skipped_sports.append(sport_key)
            continue

        reservation_id = quota_budget.reserve(
            period_key, quota_budget.SCORES, SCORES_CREDIT_COST, note=f"scores check: {sport_key}",
        )
        if reservation_id is None:
            print(f"  ::warning:: [{sport_key}] scores credit budget has no room left this period — skipping.")
            skipped_sports.append(sport_key)
            continue

        checked_sports += 1
        scores = fetch_scores(sport_key)
        quota_budget.confirm(period_key, reservation_id)
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
                try:
                    days_pending = (today - date.fromisoformat(pick['date'])).days
                except ValueError:
                    days_pending = 0
                if days_pending > STALE_PENDING_DAYS:
                    for p in all_picks:
                        if p['id'] == pick['id']:
                            p['result'] = 'unresolved'
                            p['pnl'] = None
                            break
                    print(
                        f"::warning::[{sport_key}] {pick['match']} has been pending for "
                        f"{days_pending} days with no matching score from the API (team-name "
                        f"mismatch or outside the scores endpoint's history window) — marked "
                        f"'unresolved', needs a manual check against the real result"
                    )
                else:
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

    # A pick whose sport didn't make today's cap, and is getting close to
    # falling out of the scores endpoint's 3-day history window, is
    # flagged settlement_pending_external -- distinct from the 'pending'
    # result itself (still retried normally tomorrow) and from 'unresolved'
    # (a genuine data-matching failure): this is "we didn't even get to
    # check, because of the daily budget cap, not because the data wasn't
    # there" (Section 6: "Mark missed/uncertain results
    # settlement_pending_external and report them"). Recomputed fresh
    # every run from current pending state, not left stuck on from a
    # previous run once a pick actually resolves.
    still_pending_ids = {p['id'] for p in all_picks if p['result'] == 'pending'}
    for sport_key in skipped_sports:
        for pick in by_sport[sport_key]:
            if pick['id'] not in still_pending_ids:
                continue
            try:
                days_pending = (today - date.fromisoformat(pick['date'])).days
            except ValueError:
                days_pending = 0
            urgent = days_pending >= STALE_PENDING_DAYS - 1
            for p in all_picks:
                if p['id'] == pick['id']:
                    if urgent:
                        p['settlement_pending_external'] = True
                        print(f"::warning::[{sport_key}] {pick['match']} is {days_pending}d pending and "
                              f"wasn't checked this run (daily sport-score cap) — flagged "
                              f"settlement_pending_external.")
                    else:
                        p.pop('settlement_pending_external', None)
                    break
    for p in all_picks:
        if p['result'] == 'pending' and p.get('sport_key') not in skipped_sports:
            p.pop('settlement_pending_external', None)

    # Save updated picks
    with open(PICKS_PATH, 'w') as f:
        json.dump(all_picks, f, indent=2)

    print(f"\n✅ Resolved {resolved_count} pick(s)"
          + (f" — {len(skipped_sports)} sport(s) deferred to tomorrow ({', '.join(skipped_sports)})" if skipped_sports else ""))
    return resolved_count


if __name__ == "__main__":
    resolved = check_and_resolve()

    # Print summary stats
    if os.path.exists(PICKS_PATH):
        with open(PICKS_PATH, 'r') as f:
            all_picks = json.load(f)
        settled = [p for p in all_picks if p['result'] not in ('pending', 'manual', 'unresolved', None)]
        wins = sum(1 for p in settled if p['result'] == 'win')
        losses = sum(1 for p in settled if p['result'] == 'loss')
        total_pnl = sum(p['pnl'] for p in settled if p['pnl'] is not None)
        print(f"\nAll-time: {wins}W / {losses}L | P&L: ${total_pnl:+.2f}")
