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
  5. Save data/latest_run.json via _write_run() — the single write point,
     called on EVERY exit path including empty fixtures and API failures.
     (2026-10-11, external audit, confirmed against the code: an earlier
     version of this module returned early on an empty-fixtures day
     WITHOUT writing anything, leaving a stale prior day's latest_run.json
     on disk for build_review_package.py and send_preview.py to read as if
     it were today's. Every run now writes a fresh run_id/run_date/status,
     so a stale file can never be mistaken for a fresh one downstream.)

This script never posts anything to Telegram, Instagram or Facebook, and
never sends email. Those happen later: build_review_package.py freezes the
final files + checksums, send_preview.py emails the approval request, and
publish_pick.py (after the GitHub environment approval gate) is the only
script that actually posts anywhere.
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone

import run_status

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')


def _new_run_id():
    """GITHUB_RUN_ID when running in CI; a local fallback otherwise — never
    reused across invocations, so downstream staleness checks (see
    _write_run and build_review_package.py) have something to compare."""
    return os.environ.get("GITHUB_RUN_ID") or f"local-{uuid.uuid4().hex[:12]}"


def _write_run(run_data):
    """The ONLY place latest_run.json gets written. Always fresh — run_id/
    run_ts/run_date/status are set on every call (2026-10-11, external
    audit, confirmed against the code): a prior version of this module
    returned early on an empty-fixtures day WITHOUT writing anything,
    leaving yesterday's latest_run.json (a different run_date, possibly
    has_pick=true) sitting on disk untouched. Downstream, build_review_
    package.py trusted that file's run_date as "today" and would either
    silently try to re-freeze yesterday's already-PUBLISHED pick_id (crash:
    workflow_state.InvalidTransitionError, since PUBLISHED is terminal) or,
    worse, build what looked like a fresh review package from stale data.
    Every call site below now goes through this so that can't happen again
    — including the two failure paths that used to return without writing
    anything at all."""
    os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
    with open(LATEST_RUN_PATH, 'w') as f:
        json.dump(run_data, f, indent=2)
    print(f"  Saved data/latest_run.json — run_id={run_data['run_id']} status={run_data['status']}")


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


def _recently_actioned_slugs(days=4):
    """Match slugs that already have a committed pipeline state within the
    last `days` days. Used to stop the daily pick re-selecting a fixture
    we've ALREADY posted about.

    BUG (2026-07-27): the Saturday Dragons pick landed in
    PARTIALLY_PUBLISHED (Telegram went out, but Instagram/Facebook failed
    on a dead Meta token). Every run since kept re-selecting that same
    fixture as the best value, hit the "already actioned" guard, and skipped
    the ENTIRE day — so no new picks flowed for days. Excluding by MATCH
    slug (not date) means a stuck pick_id can never trap the pipeline again:
    the next-best genuinely-new fixture is featured instead."""
    slugs = set()
    try:
        from render_brand_templates import slugify  # noqa: F401 (kept for parity)
    except Exception:
        pass
    from datetime import date, timedelta
    state_dir = os.path.join(REPO_ROOT, "data", "state")
    if not os.path.isdir(state_dir):
        return slugs
    cutoff = date.today() - timedelta(days=days)
    for name in os.listdir(state_dir):
        if not name.endswith(".json"):
            continue
        stem = name[:-5].replace("_dryrun", "")
        parts = stem.split("_", 1)
        if len(parts) != 2:
            continue
        datestr, slug = parts
        try:
            d = date.fromisoformat(datestr)  # local real `date`, mock-safe
        except ValueError:
            continue
        if d >= cutoff:
            slugs.add(slug)
    return slugs


def run():
    import fetch_odds
    from fetch_odds import fetch_upcoming_odds
    from fetch_news import fetch_news
    from generate_pick import generate_pick_for_matches

    run_id = _new_run_id()
    run_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    run_ts = datetime.now(timezone.utc).isoformat()

    print("=" * 55)
    print("PuntMate NZ — Daily Picks Pipeline (prepare only)")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print(f"run_id={run_id}")
    print("=" * 55)

    print("\n[1/3] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()

    if not matches:
        # Was this genuinely zero fixtures, or did the Odds API itself fail
        # (dead key, rate limit, timeout) for every sport? Those are very
        # different situations — one is an honest no-bet day, the other is
        # an operational failure that deserves an actionable alert, not a
        # quiet "nothing today". fetch_odds.LAST_FETCH_ERRORS distinguishes
        # them (see that module for why this isn't fetch_upcoming_odds's own
        # return value).
        had_api_errors = bool(fetch_odds.LAST_FETCH_ERRORS)
        status = run_status.ODDS_API_ERROR if had_api_errors else run_status.NO_VALUE
        reasoning = (
            f"The Odds API returned errors for {len(fetch_odds.LAST_FETCH_ERRORS)} sport(s) and no "
            f"fixtures could be fetched at all — see errors below."
            if had_api_errors else
            "No fixtures at all across any configured sport today — genuinely nothing to assess."
        )
        if had_api_errors:
            print(f"  ::error::Odds API errors on every sport — {fetch_odds.LAST_FETCH_ERRORS}")
        else:
            print("  No matches today — nothing to prepare.")
        _write_run({
            "run_id": run_id,
            "run_date": run_date,
            "run_ts": run_ts,
            "status": status,
            "pick": {"has_pick": False, "status": status, "reasoning": reasoning, "research_warnings": []},
            "odds_api_errors": fetch_odds.LAST_FETCH_ERRORS,
        })
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
    already_posted = _recently_actioned_slugs()
    if already_posted:
        print(f"  Excluding {len(already_posted)} already-posted fixture(s) from featured selection.")
    pick = generate_pick_for_matches(matches, match_news, exclude_matches=already_posted)

    if pick.get("has_pick"):
        existing_state = _already_actioned_today(pick["match"], run_date)
        if existing_state is not None:
            print(f"  ::warning:: {pick['match']} already has a pipeline state today "
                  f"(state={existing_state.get('state')}) — a fixture can only produce "
                  f"one live pick_id per calendar day. Converting this run to NO_BET "
                  f"instead of re-entering the gate or crashing on a duplicate.")
            pick = {
                "has_pick": False,
                "status": run_status.NO_VALUE,
                "reasoning": (
                    f"{pick['match']} already went through today's pipeline earlier "
                    f"(state: {existing_state.get('state')}) — skipping to avoid a "
                    f"duplicate post or a workflow-state collision."
                ),
                "research_warnings": pick.get("research_warnings", []),
            }

    run_data = {
        "run_id": run_id,
        "run_date": run_date,
        "run_ts": run_ts,
        "status": pick.get("status", run_status.NO_VALUE),
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
        _write_run(run_data)
        print(f"  {len(run_data['watchlist'])}-fixture watchlist included (no cards rendered).")
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
        # equivalent rather than freezing a pick with no images. Distinct
        # RENDER_ERROR status: this is an operational failure (a real,
        # backable pick existed), not an honest no-value day — deserves an
        # actionable alert, not routine no-bet handling.
        pick["has_pick"] = False
        pick["status"] = run_status.RENDER_ERROR
        pick["reasoning"] = f"Card rendering failed: {e}"
        run_data["pick"] = pick
        run_data["status"] = run_status.RENDER_ERROR

    _write_run(run_data)

    print("\nPipeline (prepare stage) complete")
    print("=" * 55)


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    run()
