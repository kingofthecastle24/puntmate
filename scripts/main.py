"""
main.py — PuntMate NZ daily picks pipeline
Runs via GitHub Actions on schedule.

Flow:
  1. Fetch odds (The Odds API)
  2. Value analysis → 1–2 picks above edge threshold
  3. Generate carousel PNGs (Betslip Night or Matchday Print)
  4. Post to Telegram (full analysis)
  5. Post carousel to Instagram (first slide for social discovery)
  6. Post to Facebook (optional)
  7. Log pick for weekly results tracking
"""

import sys
import os
import json
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')

# Optional integrations — only activated if secrets are set
FB_ENABLED = bool(os.environ.get('FACEBOOK_PAGE_TOKEN') and os.environ.get('FACEBOOK_PAGE_ID'))
IG_ENABLED = bool(os.environ.get('INSTAGRAM_ACCESS_TOKEN') and os.environ.get('INSTAGRAM_USER_ID'))


def save_latest_run(matches, picks):
    """Persist enriched picks to data/latest_run.json for results tracking."""
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


def _format_telegram_pick(pick):
    """Format a single pick as a Telegram message (standard Markdown)."""
    tier_emoji = {"investor": "📊", "punter": "🎯", "gambler": "🎰"}.get(pick.get("tier", "punter"), "🎯")
    dots = "●" * pick.get("confidence", 3) + "○" * (5 - pick.get("confidence", 3))
    edge = pick.get("edge_pct", "")
    edge_str = f"+{edge}%" if edge else ""

    lines = [
        f"*{tier_emoji} PUNTMATE NZ — {pick.get('sport_label', '')}*",
        "",
        f"🏟 {pick.get('match', '')}",
        "",
        f"*PICK:* {pick.get('selection', '')}",
        f"*ODDS:* {pick.get('odds', '')} ({pick.get('market', '')})",
        "",
        f"_{pick.get('analysis', '')}_",
        "",
        f"Confidence: {dots} {pick.get('confidenceLabel', '')}",
        f"Edge: {edge_str}",
        "",
        "──────────────────",
        "📲 Join Telegram for daily picks",
        "R18 · Gamble responsibly · 0800 654 655",
    ]
    return "\n".join(lines)


def run():
    from fetch_odds import fetch_upcoming_odds
    from generate_pick import generate_picks_for_matches
    from generate_picks_image import generate_carousel
    from post_telegram import post_text, send_picks_card, post_no_picks
    from post_instagram import post_carousel_to_instagram

    print("=" * 55)
    print("PuntMate NZ — Daily Picks Pipeline")
    print(datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'))
    print("=" * 55)

    # ── 1. Fetch odds ──────────────────────────────────────────────────────────
    print("\n[1/4] Fetching upcoming match odds...")
    matches = fetch_upcoming_odds()

    if not matches:
        print("  No matches today — posting hold message")
        post_no_picks()
        return

    # ── 2. Value analysis ──────────────────────────────────────────────────────
    print(f"\n[2/4] Running value analysis on {len(matches)} matches...")
    picks = generate_picks_for_matches(matches)

    if not picks:
        print("  No value picks found today — staying silent (quality > quantity)")
        # Only post if there's genuinely nothing worth betting on
        # Don't post just to post; silence is fine
        return

    print(f"  → {len(picks)} value pick(s) selected")

    # ── 3. Generate carousel images ────────────────────────────────────────────
    print(f"\n[3/4] Generating carousel cards...")
    os.makedirs(CARDS_DIR, exist_ok=True)

    all_card_sets = []  # list of [cover, tip, breakdown] per pick
    for pick in picks:
        try:
            card_paths = generate_carousel(pick, CARDS_DIR)
            all_card_sets.append(card_paths)
            look = "Matchday Print" if pick.get("big_game") else "Betslip Night"
            print(f"  ✓ {pick.get('match', '')} [{look}] → {len(card_paths)} slides")
        except Exception as e:
            print(f"  ✗ Image generation failed for {pick.get('match', '')}: {e}")
            all_card_sets.append([])

    # ── 4. Post to Telegram ────────────────────────────────────────────────────
    print(f"\n[4/4] Posting to channels...")

    for i, pick in enumerate(picks):
        msg = _format_telegram_pick(pick)
        card_set = all_card_sets[i] if i < len(all_card_sets) else []

        # Send pick slide image with full explanation as caption (one post, not two)
        # Use slide 2 (tip slide) if available — it shows the actual pick/odds
        if card_set:
            slide = card_set[1] if len(card_set) > 1 else card_set[0]
            send_picks_card(slide, caption=msg)
        else:
            # Fallback: text only if image generation failed
            post_text(msg)

    # ── 5. Instagram (carousel — all 3 slides for first pick) ─────────────────
    if IG_ENABLED and all_card_sets and all_card_sets[0]:
        print("  → Instagram")
        try:
            post_carousel_to_instagram(slide_paths=all_card_sets[0], picks=picks)
        except Exception as e:
            print(f"  ✗ Instagram error: {e}")
    else:
        print("  → Instagram (skipped — not configured)")

    # ── 6. Facebook ────────────────────────────────────────────────────────────
    if FB_ENABLED:
        print("  → Facebook")
        try:
            from post_facebook import post_pick_to_facebook
            for i, pick in enumerate(picks):
                card_set = all_card_sets[i] if i < len(all_card_sets) else []
                img = card_set[0] if card_set else None
                post_pick_to_facebook(pick, img)
        except Exception as e:
            print(f"  ✗ Facebook error: {e}")
    else:
        print("  → Facebook (skipped — not configured)")

    # ── 7. Log for results ─────────────────────────────────────────────────────
    save_latest_run(matches, picks)

    print("\n✅ Pipeline complete")
    print("=" * 55)


if __name__ == "__main__":
    required = ['ANTHROPIC_API_KEY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHANNEL_ID', 'ODDS_API_KEY']
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    run()
