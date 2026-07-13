#!/usr/bin/env python3
"""
build_social_post.py — builds data/social_post.json from data/latest_run.json,
after main.py + render_brand_templates.py have run.

This is the single artifact publish_pick.py reads later — everything it needs
(captions, image paths, image URLs, intended platforms) is decided here, once,
so the publish stage never has to regenerate or guess anything ("use the exact
artifact produced by the approved run", not "whatever's newest on disk").

Run from the scripts/ directory (matches the rest of the pipeline's convention):
    cd scripts && python build_social_post.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from render_brand_templates import slugify, choose_theme  # reuse the same logic the renderer used

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
LATEST_RUN_PATH = os.path.join(REPO_ROOT, 'data', 'latest_run.json')
SOCIAL_POST_PATH = os.path.join(REPO_ROOT, 'data', 'social_post.json')
CARDS_DIR = os.path.join(REPO_ROOT, 'data', 'cards')

TIER_EMOJI = {"investor": "📊", "punter": "🎯", "gambler": "🎰"}
RESPONSIBLE_LINE = "Problem Gambling Foundation NZ: 0800 664 262"


def raw_url(repo, filename):
    return f"https://raw.githubusercontent.com/{repo}/main/data/cards/{filename}"


def format_telegram_message(pick):
    tier = (pick.get("personality") or pick.get("tier") or "punter").lower()
    emoji = TIER_EMOJI.get(tier, "🎯")
    lines = [
        f"*{emoji} PUNTMATE NZ — {pick.get('sport', '')}*",
        "",
        f"🏟 {pick.get('match', '')}",
        "",
        f"*PICK:* {pick.get('pick', '')}",
        f"*ODDS:* {pick.get('odds', '')} ({pick.get('market', '')})",
        "",
        f"_{pick.get('reasoning', '')}_",
        "",
        f"Confidence: {pick.get('confidence', 'Medium')}",
        "",
        "──────────────────",
        "📲 Join Telegram for daily picks",
        f"R18 · Gamble responsibly · {RESPONSIBLE_LINE}",
    ]
    return "\n".join(lines)


def build_caption(picks, date_str):
    lines = [f"🏆 TODAY'S VALUE PICKS — {date_str}", ""]
    for p in picks:
        tier = (p.get("personality") or p.get("tier") or "punter").lower()
        emoji = TIER_EMOJI.get(tier, "🎯")
        lines.append(f"{emoji} {p.get('sport', '')} | {p.get('pick', '')} @ {p.get('odds', 'N/A')}")
        lines.append(f"   {p.get('reasoning', '')[:140]}")
        lines.append("")
    lines += [
        "Swipe for full breakdown 👆",
        "Follow for daily value picks → @puntmatenz",
        "",
        RESPONSIBLE_LINE,
    ]
    return "\n".join(lines)


def main():
    if not os.path.exists(LATEST_RUN_PATH):
        print("::notice::No data/latest_run.json — nothing to prepare a social post for today.")
        # Write an explicit "nothing to publish" marker so the workflow can branch on it.
        os.makedirs(os.path.dirname(SOCIAL_POST_PATH), exist_ok=True)
        with open(SOCIAL_POST_PATH, 'w') as f:
            json.dump({"has_picks": False}, f, indent=2)
        return

    with open(LATEST_RUN_PATH) as f:
        run_data = json.load(f)

    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if run_data.get("run_date") != today:
        # latest_run.json is left over from a previous day's run (today's
        # main.py found no matches/no value picks and didn't touch it) —
        # don't republish stale data.
        print(f"::notice::data/latest_run.json is from {run_data.get('run_date')}, not today ({today}) — nothing to publish.")
        with open(SOCIAL_POST_PATH, 'w') as f:
            json.dump({"has_picks": False}, f, indent=2)
        return

    picks = run_data.get("picks", [])
    if not picks:
        with open(SOCIAL_POST_PATH, 'w') as f:
            json.dump({"has_picks": False}, f, indent=2)
        return

    date_str = run_data.get("run_date") or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    repo = os.environ.get("GITHUB_REPOSITORY", "kingofthecastle24/puntmate")

    # Feature the first pick (matches the existing convention: one card set headlines the post).
    pick = picks[0]
    theme = choose_theme(pick)
    match_slug = slugify(pick.get("match") or f"{pick.get('home_team','')}_{pick.get('away_team','')}")
    base = f"{date_str}_{match_slug}_{theme}"

    filenames = {
        "cover": f"{base}_1_cover.png",
        "tip": f"{base}_2_tip.png",
        "breakdown": f"{base}_3_breakdown.png",
        "story": f"{base}_story.png",
    }
    # Only reference files that actually exist (renderer may have fallen back to
    # Pillow, which doesn't produce a story slide, or failed for this pick).
    present = {k: v for k, v in filenames.items() if os.path.exists(os.path.join(CARDS_DIR, v))}

    carousel_urls = [raw_url(repo, present[k]) for k in ("cover", "tip", "breakdown") if k in present]
    story_url = raw_url(repo, present["story"]) if "story" in present else None

    intended_platforms = ["telegram"]
    if carousel_urls:
        intended_platforms.append("instagram_feed")
    if story_url:
        intended_platforms.append("instagram_story")
    intended_platforms.append("facebook")

    post_data = {
        "has_picks": True,
        "pick_id": f"{date_str}_{match_slug}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "post_date": date_str,
        "match": pick.get("match", ""),
        "selection": pick.get("pick", ""),
        "market": pick.get("market", ""),
        "odds": pick.get("odds", ""),
        "theme": theme,
        "carousel_paths": [os.path.join("data", "cards", present[k]) for k in ("cover", "tip", "breakdown") if k in present],
        "carousel_urls": carousel_urls,
        "story_path": os.path.join("data", "cards", present["story"]) if "story" in present else None,
        "story_url": story_url,
        # Kept for backward compatibility with any script still reading a single image_url
        # (e.g. manual retries via publish.yml) — first carousel slide, or the story if that's
        # all we have.
        "image_url": (carousel_urls[0] if carousel_urls else story_url) or "",
        "caption": build_caption(picks, date_str),
        "telegram_message": format_telegram_message(pick),
        "intended_platforms": intended_platforms,
    }

    os.makedirs(os.path.dirname(SOCIAL_POST_PATH), exist_ok=True)
    with open(SOCIAL_POST_PATH, 'w') as f:
        json.dump(post_data, f, indent=2)

    print(f"Saved data/social_post.json — pick_id={post_data['pick_id']}, "
          f"platforms={intended_platforms}")
    print(f"  Carousel: {len(carousel_urls)} slide(s), Story: {'yes' if story_url else 'no'}")


if __name__ == "__main__":
    main()
