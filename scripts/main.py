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


def render_multi_cards(pick, tier, legs):
    """Render one multi tier's graphic (cover/legs/breakdown) via the
    Multi.dc.html brand template. Unlike the single featured pick, there is
    no legacy Pillow fallback for multis (that renderer has no multi
    support) — if Playwright rendering fails, the tier's TEXT post can still
    go to Telegram; it just won't have an Instagram graphic that run, which
    publish_pick.py handles by skipping Instagram for that tier cleanly
    rather than failing the whole pipeline over an optional secondary post.
    """
    try:
        from render_brand_templates import render_multi
        result = render_multi(pick, tier, legs, out_dir=CARDS_DIR)
        print(f"  Rendered {tier} multi cards: {result.get('files')}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  ::warning:: {w}")
        return result
    except Exception as e:
        print(f"  ::warning:: {tier} multi card rendering failed ({e}) — that tier's Telegram text can "
              f"still post, but it will have no Instagram graphic this run.")
        return None


def _already_actioned_today(match_name, run_date):
    """Guards against the run #51 crash (2026-07-18): a same-day re-run
    (manual or scheduled) can independently select the SAME fixture a
    previous run already turned into a live pick_id today. pick_id is
    date+slugified-match only for live (non-dry-run) picks, so the second
    run computes an identical pick_id to one that's already GENERATED (or
    further along: AWAITING_APPROVAL/APPROVED/PUBLISHED/REJECTED/etc).
    send_preview.py's very first call is
    workflow_state.transition(pick_id, GENERATED, ...), and GENERATED is
    only a valid target when the pick_id has NO existing state yet — so
    transitioning an already-actioned pick_id back to GENERATED always
    raises InvalidTransitionError, uncaught, crashing the generate job
    with exit code 1 (exactly what happened on run #51: run #50 published
    a live pick for a fixture 12 minutes earlier in the same odds window,
    and the following scheduled run picked the same fixture again).

    This existed for dry-run-vs-live collisions already (see
    build_review_package.py's "_dryrun" suffix, commit 7dcfbc7) but never
    for live-vs-live collisions within the same calendar day — this closes
    that gap at the source, before a pick_id is ever computed, instead of
    letting a downstream script crash on it.

    Returns the existing state dict if this match already has ANY state
    recorded for today's date, else None.
    """
    try:
        from render_brand_templates import slugify
        from workflow_state import load_state
    except Exception as e:
        # Never let a defensive check itself crash the pipeline.
        print(f"  ::warning:: dedupe check failed to import ({e}) — proceeding without it.")
        return None

    live_pick_id = f"{run_date}_{slugify(match_name)}"
    return load_state(REPO_ROOT, live_pick_id)


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

    run_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if pick.get("has_pick"):
        existing_state = _already_actioned_today(pick["match"], run_date)
        if existing_state is not None:
            print(f"  ::warning:: {pick['match']} already has a pipeline state today "
                  f"(state={existing_state.get('state')}) — a fixture can only produce "
                  f"one live pick_id per calendar day. Converting this run to NO_BET "
                  f"instead of re-entering the gate or crashing on a duplicate.")
            pick = {
                "has_pick": False,
                "reasoning": (
                    f"{pick['match']} already went through today's pipeline earlier "
                    f"(state: {existing_state.get('state')}) — skipping to avoid a "
                    f"duplicate post or a workflow-state collision."
                ),
                "research_warnings": pick.get("research_warnings", []),
            }

    run_data = {
        "run_date": run_date,
        "run_ts": datetime.now(timezone.utc).isoformat(),
        "pick": pick,
    }

    if not pick.get("has_pick"):
        print(f"  NO_BET — {pick.get('reasoning', '')}")
        # Phase 4: on a genuine NO_BET day, prepare a lightweight Watchlist —
        # the day's most interesting fixtures (sport-priority order, same
        # ordering fetch_upcoming_odds returns), with NO selections and NO
        # odds framed as advice. This gives followers honest content on a
        # no-bet day without manufacturing a pick.
        run_data["watchlist"] = [
            {
                "match": m["match"],
                "sport_label": m.get("sport_label") or m.get("sport", ""),
                "kickoff": m.get("kickoff", ""),
            }
            for m in matches[:5]
        ]
        os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
        with open(LATEST_RUN_PATH, 'w') as f:
            json.dump(run_data, f, indent=2)
        print(f"  Saved NO_BET result + {len(run_data['watchlist'])}-fixture watchlist to data/latest_run.json (no cards rendered).")
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

        # 2026-07-19 (Micah): Punter/Gambler-Degenerate multis are no longer
        # built from a single day's fixtures at all — generate_pick_for_matches
        # is called here with build_multis defaulting to False, so
        # pick["punter_multi_legs"]/["gambler_multi_legs"] are always empty
        # for this daily run. Multis are now exclusively assembled from the
        # full Fri/Sat/Sun fixture pool by the separate weekend job (see
        # generate_weekend_multi.py, which reuses render_multi_cards below).
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
