"""
main.py — PuntMate NZ daily picks pipeline (PREPARE stage only)

Flow:
  1. Fetch odds (The Odds API)
  2. Value analysis → 1-2 picks above edge threshold
  3. Render carousel + Story PNGs for the picks (Playwright brand-kit
     renderer, falls back to the legacy Pillow renderer if that fails)
  4. Save data/latest_run.json

IMPORTANT: this script no longer posts anything to Telegram, Instagram or
Facebook. Publishing was moved behind the approval gate — see
scripts/publish_pick.py, which .github/workflows/generate.yml's "publish"
job runs only after a human approves the rendered preview. That's a
deliberate change: this used to post to Telegram immediately, before any
review, which meant Telegram had no approval step at all while Instagram/
Facebook did. Now all platforms wait for the same approval.

If no matches or no value picks are found, this script exits cleanly
without writing latest_run.json — the workflow checks for that and skips
straight to "nothing to publish today" rather than proceeding.
"""

import sys
import os
import json
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')


def save_latest_run(matches, picks):
    """Persist enriched picks to data/latest_run.json for results tracking
    and for the renderer/publish stages to read."""
    match_lookup = {m['match']: m for m in matches}
    enriched = []
    for pick in picks:
        raw = match_lookup.get(pick.get('match'), {})
        enriched.append({
            **pick,
            "sport_key":  raw.get('sport', ''),
            "home_team":  raw.get('home_team', pick.get('home_team', '')),
            "away_team":  raw.get('away_team', pick.get('away_team', '')),
            "result":     "PENDING",  # updated by check_results.py
        })

    run_data = {
        "run_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "run_ts":   datetime.now(timezone.utc).isoformat(),
        "picks":    enriched,
    }

    os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
    with open(LATEST_RUN_PATH, 'w') as f:
        json.dump(run_data, f, indent=2)

    print(f"  Saved {len(enriched)} pick(s) to data/latest_run.json")
    return run_data


def render_cards(picks):
    """Render carousel + Story PNGs for each pick. Tries the Playwright
    brand-kit renderer first (scripts/render_brand_templates.py); falls back
    to the legacy Pillow renderer (generate_picks_image.py) per-pick if that
    raises. Returns a list of dicts, one per pick, each either
    {"cover":..., "tip":..., "breakdown":..., "story":..., "renderer": "playwright"}
    or the Pillow 3-slide list under "renderer": "pillow" (no story slide —
    the Pillow path never produced one), or {} if both failed.
    """
    os.makedirs(CARDS_DIR, exist_ok=True)
    from render_brand_templates import render_pick as render_pick_playwright

    results = []
    for pick in picks:
        try:
            result = render_pick_playwright(pick, out_dir=CARDS_DIR)
            print(f"  ✓ {pick.get('match', '')} [{result['theme']}] → playwright renderer, "
                  f"{len(result['warnings'])} warning(s)")
            results.append({**result["files"], "renderer": "playwright", "warnings": result["warnings"]})
            continue
        except Exception as e:
            print(f"  ⚠️  Playwright renderer failed for {pick.get('match', '')}: {e}")
            print("     Falling back to legacy Pillow renderer...")

        try:
            from generate_picks_image import generate_carousel
            card_paths = generate_carousel(pick, CARDS_DIR)
            look = "Matchday Print" if pick.get("big_game") else "Betslip Night"
            print(f"  ✓ {pick.get('match', '')} [{look}] → Pillow fallback, {len(card_paths)} slides")
            results.append({
                "cover": card_paths[0] if len(card_paths) > 0 else None,
                "tip": card_paths[1] if len(card_paths) > 1 else None,
                "breakdown": card_paths[2] if len(card_paths) > 2 else None,
                "story": None,
                "renderer": "pillow",
                "warnings": ["Pillow fallback used — no Story image produced"],
            })
        except Exception as e:
            print(f"  ✗ Both renderers failed for {pick.get('match', '')}: {e}")
            results.append({})

    return results


def run():
    from fetch_odds import fetch_upcoming_odds
    from generate_pick import generate_picks_for_matches

    print("=" * 55)
    print("PuntMate NZ — Daily Picks Pipeline (prepare stage)")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("=" * 55)

    # -- 1. Fetch odds --------------------------------------------------------
    print("\n[1/3] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()

    if not matches:
        print("  No matches today — nothing to prepare")
        return None

    # -- 2. Value analysis -----------------------------------------------------
    print(f"\n[2/3] Running value analysis on {len(matches)} matches...")
    picks = generate_picks_for_matches(matches)

    if not picks:
        print("  No value picks found today — staying silent (quality > quantity)")
        return None

    print(f"  -> {len(picks)} value pick(s) selected")

    # Enrich + save first so the renderer gets sport_key/home_team/away_team
    # (added during enrichment) rather than the raw generate_pick.py output.
    run_data = save_latest_run(matches, picks)

    # -- 3. Render carousel + Story images --------------------------------------
    # Only render the FEATURED pick (picks[0] — build_social_post.py always
    # features the first pick). Rendering all personalities' picks used to
    # cause a real bug: when two personalities land on the same match
    # (e.g. investor/punter pick France, gambler picks Spain on the same
    # France v Spain match), every render shares the same filename
    # (date_match_theme_*), so whichever pick rendered last silently
    # overwrote the featured pick's images on disk — caption said "France",
    # card showed "Spain". Rendering only the featured pick removes the
    # collision entirely and skips wasted renders for picks nobody publishes.
    print(f"\n[3/3] Rendering carousel + Story cards for the featured pick...")
    featured_pick = run_data["picks"][0]
    card_sets = render_cards([featured_pick])
    run_data["card_sets"] = card_sets

    # card_sets isn't part of the on-disk schema (paths would go stale) —
    # persist picks/run metadata only; card_sets is returned in-memory for
    # build_social_post.py to consume within the same job.
    with open(LATEST_RUN_PATH, 'w') as f:
        json.dump({k: v for k, v in run_data.items() if k != "card_sets"}, f, indent=2)

    print("\nPrepare stage complete — nothing has been posted yet.")
    print("=" * 55)
    return run_data


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    result = run()
    # Exit code 0 either way — "nothing to publish today" is a normal outcome,
    # not a pipeline failure. The workflow checks data/latest_run.json's
    # freshness (via the has_picks output) to decide whether to continue to
    # render/approve/publish or stop here.
    sys.exit(0)
