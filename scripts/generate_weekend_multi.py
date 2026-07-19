#!/usr/bin/env python3
"""
generate_weekend_multi.py — PuntMate NZ weekend Punter/Gambler-Degenerate
multi pipeline (PREPARE stage only).

2026-07-19 (Micah): "You might have better picks from reviewing the bets
over the complete weekend vs just the day" — plus "I don't want the
gambler/degen multi to run everyday because it might ruin the strike rate
and therefore the reputation." Both multi tiers are now built EXCLUSIVELY
here, from a single widened fixture pool spanning Friday through Sunday
(~76 hours from this job's run time), instead of independently per day.
The ordinary daily run (main.py) never builds multis at all any more (see
generate_pick.generate_pick_for_matches's build_multis flag, default False)
— so neither tier can ever fire on a random weekday, which is exactly what
guarantees the Gambler/Degenerate multi only ever shows up around the
weekend, addressing the reputation concern directly.

This script does NOT select a featured single pick — that's still the daily
job's job, every day including weekends. It only ever produces the two
multi tiers (Punter / Gambler-Degenerate), each independently subject to
the same 3-leg floor and never-forced rule as before.

Meant to run once, on the Friday 7am NZT job (see .github/workflows/
generate.yml), ahead of that day's regular daily pick.

Flow (mirrors main.py):
  1. Fetch odds across the widened weekend window (fetch_odds.fetch_upcoming_odds
     with hours_ahead=WEEKEND_HOURS_AHEAD)
  2. Fetch + validate research for every fixture, same as the daily run
  3. generate_pick_for_matches(..., build_multis=True) -> punter_multi_legs /
     gambler_multi_legs pooled across the whole weekend
  4. Render each qualifying tier's graphic (reuses main.py's render_multi_cards)
  5. Save data/latest_weekend_run.json

Never posts anything to any platform. build_weekend_multi_package.py (the
freeze step) and publish_pick.py handle everything after this, through the
same approval-gated flow as the daily pick.
"""
import os
import sys
import json
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_WEEKEND_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_weekend_run.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')

# Friday 7am to end of Sunday NZT is roughly 76 hours (Fri 7am -> Mon
# ~11am). A little slack past midnight Sunday is deliberate -- late Sunday
# night fixtures (NZT) are still genuinely "the weekend" for this audience.
WEEKEND_HOURS_AHEAD = 76

# A synthetic anchor "pick" -- there is no single featured match for a
# weekend multi, but render_multi()/choose_theme()/slugify() all expect a
# pick-shaped dict for filename/theme purposes. "Weekend Multi" never
# matches BIG_GAME_SPORTS/BIG_GAME_KEYWORDS, so it always renders on the
# standard Betslip Night (dark) theme -- a deliberate, simple default.
def _weekend_anchor_pick(run_date):
    return {
        "match": "Weekend Multi",
        "home_team": "Weekend",
        "away_team": "Multi",
        "sport": "",
        "sport_key": "",
        "kickoff": f"{run_date}T00:00:00Z",
    }


def run():
    from fetch_odds import fetch_upcoming_odds
    from fetch_news import fetch_news
    from generate_pick import generate_pick_for_matches
    from main import render_multi_cards  # reuse the exact same render/skip-on-failure logic

    print("=" * 55)
    print("PuntMate NZ — Weekend Multi Pipeline (prepare only)")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("=" * 55)

    print(f"\n[1/3] Fetching fixtures across the next {WEEKEND_HOURS_AHEAD}h (the whole weekend)...")
    matches = fetch_upcoming_odds(hours_ahead=WEEKEND_HOURS_AHEAD)

    run_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    run_data = {
        "run_date": run_date,
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "hours_ahead": WEEKEND_HOURS_AHEAD,
        "fixture_count": len(matches),
    }

    if not matches:
        print("  No fixtures in the weekend window — nothing to prepare.")
        run_data["punter_multi_legs"] = []
        run_data["gambler_multi_legs"] = []
        os.makedirs(os.path.dirname(LATEST_WEEKEND_RUN_PATH), exist_ok=True)
        with open(LATEST_WEEKEND_RUN_PATH, 'w') as f:
            json.dump(run_data, f, indent=2)
        return

    print(f"\n[2/3] Fetching + validating research for {len(matches)} fixture(s)...")
    match_news = {}
    for m in matches:
        try:
            news = fetch_news(m)
            match_news[m["match"]] = news
            if news.get("warnings"):
                for w in news["warnings"]:
                    print(f"  ::notice:: [{m['match']}] {w}")
        except Exception as e:
            print(f"  Research fetch failed for {m['match']}: {e}")
            match_news[m["match"]] = {"text": "", "accepted_count": 0, "warnings": [f"fetch error: {e}"], "confidence_ceiling": "LOW"}

    print("\n[3/3] Assembling the weekend Punter Multi and Gambler/Degenerate Multi...")
    pick = generate_pick_for_matches(matches, match_news, build_multis=True)

    punter_legs = pick.get("punter_multi_legs") or []
    gambler_legs = pick.get("gambler_multi_legs") or []
    print(f"  Punter Multi: {len(punter_legs)} leg(s)" + (" — below the 3-leg floor, no multi this weekend." if len(punter_legs) < 3 else ""))
    print(f"  Gambler/Degenerate Multi: {len(gambler_legs)} leg(s)" + (" — below the 3-leg floor, no multi this weekend." if len(gambler_legs) < 3 else ""))

    anchor_pick = _weekend_anchor_pick(run_date)
    os.makedirs(CARDS_DIR, exist_ok=True)
    for tier, legs in (("punter", punter_legs), ("gambler", gambler_legs)):
        if len(legs) >= 3:
            render_multi_cards(anchor_pick, tier, legs)

    run_data["punter_multi_legs"] = punter_legs
    run_data["punter_multi_promo_hint"] = pick.get("punter_multi_promo_hint")
    run_data["gambler_multi_legs"] = gambler_legs
    run_data["gambler_multi_promo_hint"] = pick.get("gambler_multi_promo_hint")
    run_data["research_warnings"] = pick.get("research_warnings", [])
    run_data["anchor_pick"] = anchor_pick

    os.makedirs(os.path.dirname(LATEST_WEEKEND_RUN_PATH), exist_ok=True)
    with open(LATEST_WEEKEND_RUN_PATH, 'w') as f:
        json.dump(run_data, f, indent=2)
    print("\nSaved data/latest_weekend_run.json")
    print("Pipeline (prepare stage) complete")
    print("=" * 55)


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    run()
