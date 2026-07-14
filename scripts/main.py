"""
main.py — PuntMate NZ daily picks pipeline (PREPARE stage only).

Flow:
  1. Fetch odds (The Odds API)
  2. Fetch + validate research/news for every candidate match (fetch_news.py,
     backed by research_validator.py — rejects irrelevant-sport contamination)
  3. Generate ONE official pick (or NO_BET) via generate_pick.py — deterministic
     risk + bet-type classification, no personalities
  4. Render carousel + Story PNGs for the pick (Playwright brand-kit renderer,
     falls back to the legacy Pillow renderer if that fails) — skipped entirely
     for NO_BET, there is nothing to render
  5. Save data/latest_run.json

This script never posts anything to Telegram, Instagram or Facebook, and
never sends email. Those happen later: build_review_package.py freezes the
final files + checksums, send_preview.py emails the approval request, and
publish_pick.py (after the GitHub environment approval gate) is the only
script that actually posts anywhere.
"""

import os
import sys
import json
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')


def _legacy_pillow_pick(pick):
    """The legacy Pillow renderer (generate_picks_image.py) expects the
    already-mapped props shape (matchup/sportTag/etc, confidence as 1-5 dots)
    rather than the raw pick dict — build_props() is the single source of
    truth for that mapping, reused here so the fallback never drifts from
    what the Playwright path renders."""
    from render_brand_templates import build_props, pick_palette
    from datetime import datetime, timezone
    props = build_props(pick)
    return {
        **props,
        "match": props["matchup"],
        "sport_label": props["sportTag"],
        "palette": pick_palette(datetime.now(timezone.utc)),
        "big_game": pick.get("big_game", False),
    }


def render_card(pick):
    """Render one pick's cards. Tries the Playwright brand-kit renderer
    first; falls back to the legacy Pillow renderer on any exception (kept
    intentionally — documented fallback, not removed)."""
    try:
        from render_brand_templates import render_pick
        return render_pick(pick, out_dir=CARDS_DIR)
    except Exception as e:
        print(f"  Playwright renderer failed ({e}) — falling back to legacy Pillow renderer.")
        from generate_picks_image import generate_carousel
        paths = generate_carousel(_legacy_pillow_pick(pick), CARDS_DIR)
        return {"ok": True, "files": {"carousel": paths}, "warnings": ["used legacy Pillow fallback"]}


def run():
    from fetch_odds import fetch_upcoming_odds
    from fetch_news import fetch_news
    from generate_pick import generate_pick_for_matches

    print("=" * 55)
    print("PuntMate NZ — Daily Picks Pipeline (prepare only)")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("=" * 55)

    print("\n[1/3] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()

    if not matches:
        print("  No matches today — nothing to prepare. Staying silent (existing behaviour).")
        return

    print(f"\n[2/3] Fetching + validating research for {len(matches)} match(es)...")
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

    print(f"\n[3/3] Selecting one official pick...")
    pick = generate_pick_for_matches(matches, match_news)

    run_data = {
        "run_date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "pick": pick,
    }

    if not pick.get("has_pick"):
        print(f"  NO_BET — {pick.get('reasoning', '')}")
        os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
        with open(LATEST_RUN_PATH, 'w') as f:
            json.dump(run_data, f, indent=2)
        print("  Saved NO_BET result to data/latest_run.json (no cards rendered).")
        return

    print(f"  -> {pick['match']} | {pick['selection']} @ {pick['odds']} | "
          f"{pick['bet_type']} / {pick['risk']} / {pick['confidence']} confidence")

    os.makedirs(CARDS_DIR, exist_ok=True)
    try:
        render_result = render_card(pick)
        print(f"  Rendered cards: {render_result.get('files')}")
        if render_result.get("warnings"):
            for w in render_result["warnings"]:
                print(f"  ::warning:: {w}")
    except Exception as e:
        print(f"  ERROR: card rendering failed entirely: {e}")
        # Without cards there is nothing safe to publish — record as NO_BET
        # equivalent rather than freezing a pick with no images.
        pick["has_pick"] = False
        pick["reasoning"] = f"Card rendering failed: {e}"
        run_data["pick"] = pick

    os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
    with open(LATEST_RUN_PATH, 'w') as f:
        json.dump(run_data, f, indent=2)
    print("  Saved data/latest_run.json")

    print("\nPipeline (prepare stage) complete")
    print("=" * 55)


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    run()
