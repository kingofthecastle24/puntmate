#!/usr/bin/env python3
"""
build_review_package.py — builds the frozen review package for one pick,
after generate_pick.py has produced a verdict and render_brand_templates.py
has rendered the cards (or after a NO_BET verdict, in which case no cards
exist and no publish step will ever run for this pick_id).

Writes to data/review/<pick_id>/:
  telegram-post.txt        — exact, final Telegram message text
  instagram-caption.txt    — exact, final Instagram caption (+ hashtags)
  post-metadata.json       — full internal metadata (classification, risk,
                              confidence, research warnings, run/state info —
                              everything Gmail/Dispatch previews need)
  manifest.json            — SHA-256 checksum of every file above + every
                              final image asset, so publish_pick.py can
                              refuse to publish anything that's changed since
                              approval
  preview.html             — static preview for the GitHub artifact / job
                              summary link
  cover.png / tip.png / breakdown.png / story.png — copies of the rendered
                              cards (present only when there is a pick)

Everything written here is what gets frozen. Nothing after this point may be
regenerated — publish_pick.py reloads these exact files and verifies them
against manifest.json before posting anything.
"""
import html
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from render_brand_templates import slugify, choose_theme
from manifest import build_manifest, write_manifest
from copy_validator import validate_post, CopyValidationError

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
LATEST_RUN_PATH = os.path.join(REPO_ROOT, "data", "latest_run.json")
CARDS_DIR = os.path.join(REPO_ROOT, "data", "cards")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")

RESPONSIBLE_LINE = "Problem Gambling Foundation NZ: 0800 664 262"


def raw_url(repo, filename):
    return f"https://raw.githubusercontent.com/{repo}/main/data/cards/{filename}"


def build_telegram_text(pick):
    lines = [
        f"*🎯 PUNTMATE NZ — {pick['sport_label']}*",
        "",
        f"🏟 {pick['match']}",
        "",
        f"*PICK:* {pick['selection']}",
        f"*ODDS:* {pick['odds']} ({pick['market']})",
        f"*{pick['bet_type_label']}*",
        "",
        f"_{pick['final_explanation']}_",
    ]
    if pick.get("public_caution"):
        lines += ["", pick["public_caution"]]
    lines += [
        "",
        "──────────────────",
        "📲 Join Telegram for daily picks",
        f"R18 · Gamble responsibly · {RESPONSIBLE_LINE}",
    ]
    return "\n".join(lines)


def build_instagram_caption(pick):
    lines = [
        f"🎯 {pick['sport_label']} — {pick['match']}",
        "",
        f"{pick['selection']} @ {pick['odds']} ({pick['market']})",
        pick["bet_type_label"],
        "",
        pick["bet_type_reason"],
    ]
    if pick.get("public_caution"):
        lines += ["", pick["public_caution"]]
    lines += [
        "",
        "Follow for daily value picks → @puntmatenz",
        "",
        RESPONSIBLE_LINE,
        "",
        "#PuntmateNZ #SportsBetting #NZTAB #" + pick["sport_label"].replace(" ", ""),
    ]
    return "\n".join(lines)


def build_preview_html(pick, metadata, image_files):
    imgs = "".join(f'<img src="{f}" style="max-width:340px;margin:8px;border-radius:8px" />' for f in image_files)
    rows = "".join(
        f"<tr><td style='padding:4px 12px;color:#888'>{html.escape(str(k))}</td>"
        f"<td style='padding:4px 12px'>{html.escape(str(v))}</td></tr>"
        for k, v in metadata.items() if k not in ("research_warnings",)
    )
    warnings = "".join(f"<li>{html.escape(w)}</li>" for w in metadata.get("research_warnings", []))
    warnings_block = f"<h3>Internal research warnings (never public)</h3><ul>{warnings}</ul>" if warnings else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PuntMate review — {html.escape(metadata.get('pick_id',''))}</title></head>
<body style="font-family:sans-serif;max-width:800px;margin:24px auto">
<h1>PuntMate Post Approval Preview</h1>
<div>{imgs}</div>
<h3>Telegram</h3><pre style="white-space:pre-wrap;background:#f5f5f5;padding:12px;border-radius:8px">{html.escape(pick.get('_telegram_text',''))}</pre>
<h3>Instagram caption</h3><pre style="white-space:pre-wrap;background:#f5f5f5;padding:12px;border-radius:8px">{html.escape(pick.get('_instagram_caption',''))}</pre>
<h3>Metadata</h3><table>{rows}</table>
{warnings_block}
</body></html>"""


def build_no_bet_metadata(reasoning, research_warnings, run_id, post_date):
    return {
        "has_pick": False,
        "pick_id": f"{post_date}_no-bet",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "post_date": post_date,
        "classification": "NO_BET",
        "risk": "NO_BET",
        "bet_type": "NO_BET",
        "reasoning": reasoning,
        "research_warnings": research_warnings,
        "intended_platforms": [],
        "workflow_state": "GENERATED",
    }


def main():
    if not os.path.exists(LATEST_RUN_PATH):
        print("::notice::No data/latest_run.json — nothing to build a review package for.")
        return None

    with open(LATEST_RUN_PATH) as f:
        run_data = json.load(f)

    pick = run_data.get("pick")
    post_date = run_data.get("run_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    run_id = os.environ.get("GITHUB_RUN_ID", "local")

    if not pick or not pick.get("has_pick"):
        reasoning = (pick or {}).get("reasoning", "No matches available today.")
        warnings = (pick or {}).get("research_warnings", [])
        metadata = build_no_bet_metadata(reasoning, warnings, run_id, post_date)
        review_dir = os.path.join(REVIEW_ROOT, metadata["pick_id"])
        os.makedirs(review_dir, exist_ok=True)
        with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"NO_BET today — wrote {metadata['pick_id']}/post-metadata.json (no approval/publish needed).")
        return metadata

    repo = os.environ.get("GITHUB_REPOSITORY", "kingofthecastle24/puntmate")
    theme = choose_theme(pick)
    match_slug = slugify(pick["match"])
    base = f"{post_date}_{match_slug}_{theme}"
    pick_id = f"{post_date}_{match_slug}"

    filenames = {
        "cover": f"{base}_1_cover.png",
        "tip": f"{base}_2_tip.png",
        "breakdown": f"{base}_3_breakdown.png",
        "story": f"{base}_story.png",
    }
    present = {k: v for k, v in filenames.items() if os.path.exists(os.path.join(CARDS_DIR, v))}
    if not present:
        raise RuntimeError(f"No rendered cards found for pick_id={pick_id} — refusing to build a review package without images.")

    review_dir = os.path.join(REVIEW_ROOT, pick_id)
    os.makedirs(review_dir, exist_ok=True)

    # Copy final image assets into the review package so it's self-contained
    # and every published byte is checksummed together in one place.
    review_image_names = {}
    for key, fname in present.items():
        dest_name = f"{key}.png"
        shutil.copyfile(os.path.join(CARDS_DIR, fname), os.path.join(review_dir, dest_name))
        review_image_names[key] = dest_name

    telegram_text = build_telegram_text(pick)
    instagram_caption = build_instagram_caption(pick)

    # Deterministic copy-consistency validation — this MUST pass before
    # anything is frozen. If it doesn't, we abort loudly rather than freeze
    # unsafe copy.
    validate_post(
        {"risk": pick["risk"], "bet_type": pick["bet_type"], "classification": pick["risk"], "selection": pick["selection"]},
        telegram_text, instagram_caption,
    )

    carousel_urls = [raw_url(repo, present[k]) for k in ("cover", "tip", "breakdown") if k in present]
    story_url = raw_url(repo, present["story"]) if "story" in present else None

    intended_platforms = ["telegram"]
    if carousel_urls:
        intended_platforms.append("instagram_feed")
    if story_url:
        intended_platforms.append("instagram_story")
    intended_platforms.append("facebook")  # via linked Instagram only — see publish_pick.py

    metadata = {
        "has_pick": True,
        "pick_id": pick_id,
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "post_date": post_date,
        "match": pick["match"],
        "sport": pick["sport"],
        "sport_label": pick["sport_label"],
        "market": pick["market"],
        "selection": pick["selection"],
        "odds": pick["odds"],
        "bet_type": pick["bet_type"],
        "bet_type_label": pick["bet_type_label"],
        "bet_type_reason": pick["bet_type_reason"],
        "classification": pick["risk"],
        "risk": pick["risk"],
        "confidence": pick["confidence"],
        "confidence_label": pick["confidence_label"],
        "final_explanation": pick["final_explanation"],
        "public_caution": pick.get("public_caution"),
        "research_warnings": pick.get("research_warnings", []),
        "theme": theme,
        "carousel_paths": [os.path.join("data", "review", pick_id, review_image_names[k]) for k in ("cover", "tip", "breakdown") if k in review_image_names],
        "carousel_urls": carousel_urls,
        "story_path": os.path.join("data", "review", pick_id, review_image_names["story"]) if "story" in review_image_names else None,
        "story_url": story_url,
        "intended_platforms": intended_platforms,
        "workflow_state": "GENERATED",
    }

    with open(os.path.join(review_dir, "telegram-post.txt"), "w") as f:
        f.write(telegram_text)
    with open(os.path.join(review_dir, "instagram-caption.txt"), "w") as f:
        f.write(instagram_caption)
    with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    pick["_telegram_text"] = telegram_text
    pick["_instagram_caption"] = instagram_caption
    preview_html = build_preview_html(pick, metadata, list(review_image_names.values()))
    with open(os.path.join(review_dir, "preview.html"), "w") as f:
        f.write(preview_html)

    # Manifest covers every file that publish_pick.py will actually read —
    # texts, metadata, images, preview. Written LAST, after everything else exists.
    manifest_files = ["telegram-post.txt", "instagram-caption.txt", "post-metadata.json", "preview.html"] + list(review_image_names.values())
    manifest = build_manifest(review_dir, manifest_files, extra={
        "pick_id": pick_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    write_manifest(manifest, os.path.join(review_dir, "manifest.json"))

    print(f"Built review package: data/review/{pick_id}/ ({len(manifest_files)} files checksummed)")
    return metadata


if __name__ == "__main__":
    main()
