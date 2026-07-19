#!/usr/bin/env python3
"""
build_weekend_multi_package.py — freezes the weekend Punter Multi and
Gambler/Degenerate Multi (from generate_weekend_multi.py's
data/latest_weekend_run.json) as their OWN standalone, approvable post.

pick_id = "{run_date}_weekend_multi" (+ "_dryrun" suffix in dry-run mode,
same convention as every other pick_id — see build_review_package.py's
module docstring). This goes through the EXACT SAME workflow_state /
manifest / Gmail preview / GitHub approval gate / Telegram+Instagram
publish machinery as the daily single pick — send_preview.py and
publish_pick.py both have a dedicated branch for this post shape
(is_weekend_multi=True, has_pick=False, has_punter_multi/has_gambler_multi
set independently), they don't need a separate script per post type.

There is no featured single pick here — main.py's daily job still runs
every day and still produces its own single pick, completely independently
of this. This script only ever produces the two multi tiers.

Writes to data/review/<pick_id>/:
  punter-multi-post.txt / gambler-multi-post.txt — present only if that
    tier cleared 3 legs
  punter_multi_{cover,legs,breakdown}.png / gambler_multi_{...}.png —
    present only if that tier's graphic was rendered
  post-metadata.json, manifest.json, preview.html — always present
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from render_brand_templates import slugify, choose_theme
from manifest import build_manifest, write_manifest
from copy_validator import validate_text
import build_review_package as brp

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
LATEST_WEEKEND_RUN_PATH = os.path.join(REPO_ROOT, "data", "latest_weekend_run.json")
CARDS_DIR = os.path.join(REPO_ROOT, "data", "cards")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")


def main():
    with open(LATEST_WEEKEND_RUN_PATH) as f:
        run_data = json.load(f)

    run_date = run_data["run_date"]
    punter_legs = run_data.get("punter_multi_legs") or []
    gambler_legs = run_data.get("gambler_multi_legs") or []
    pick_id = f"{run_date}_weekend_multi{brp._pick_id_suffix()}"
    review_dir = os.path.join(REVIEW_ROOT, pick_id)
    os.makedirs(review_dir, exist_ok=True)

    metadata = {
        "has_pick": False,  # no single featured selection — this post is multis only
        "is_weekend_multi": True,
        "pick_id": pick_id,
        "post_date": run_date,
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_warnings": run_data.get("research_warnings", []),
        "reasoning": "Neither the Punter Multi nor the Gambler/Degenerate Multi cleared the 3-leg floor this weekend.",
        "workflow_state": "GENERATED",
    }

    if len(punter_legs) < 3 and len(gambler_legs) < 3:
        # Explicit False flags — publish_pick keys off these (stale-file fix)
        metadata["has_punter_multi"] = False
        metadata["has_gambler_multi"] = False
        with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        manifest = build_manifest(review_dir, ["post-metadata.json"], extra={
            "pick_id": pick_id, "created_at": datetime.now(timezone.utc).isoformat(),
        })
        write_manifest(manifest, os.path.join(review_dir, "manifest.json"))
        print(f"Weekend multi: neither tier cleared 3 legs — wrote {pick_id}/post-metadata.json only.")
        return metadata

    anchor_pick = run_data.get("anchor_pick") or {"match": "Weekend Multi", "home_team": "Weekend", "away_team": "Multi"}
    theme = choose_theme(anchor_pick)
    match_slug = slugify(anchor_pick["match"])
    base = f"{run_date}_{match_slug}_{theme}"
    repo = os.environ.get("GITHUB_REPOSITORY", "kingofthecastle24/puntmate")

    manifest_files = []
    intended_platforms = set()
    tier_texts = {}

    def _freeze_tier(tier_key, legs, promo_hint, build_text_fn, bet_type_label):
        if len(legs) < 3:
            # Same stale-file cleanup as build_review_package (dry run #56
            # bug): a Friday re-run of the same weekend pick_id must not
            # leave a previously-frozen tier's files behind when that tier
            # doesn't fire this time.
            metadata[f"has_{tier_key}_multi"] = False
            for name in [f"{tier_key}-multi-post.txt"] + [f"{tier_key}_multi_{k}.png" for k in ("cover", "legs", "breakdown")]:
                stale_path = os.path.join(review_dir, name)
                if os.path.exists(stale_path):
                    os.remove(stale_path)
                    print(f"  Removed stale {name} from a previous run of this weekend pick_id.")
            return
        pick_for_text = {f"{tier_key}_multi_legs": legs}
        text = build_text_fn(pick_for_text)
        validate_text(text, risk="RISKY_PICK", bet_type=bet_type_label, public=True)
        tier_texts[tier_key] = text
        text_filename = f"{tier_key}-multi-post.txt"
        with open(os.path.join(review_dir, text_filename), "w") as f:
            f.write(text)
        manifest_files.append(text_filename)
        metadata[f"has_{tier_key}_multi"] = True
        intended_platforms.add("telegram")
        if promo_hint:
            metadata[f"{tier_key}_multi_promo_hint"] = promo_hint

        multi_filenames = {
            "cover": f"{base}_{tier_key}_multi_1_cover.png",
            "legs": f"{base}_{tier_key}_multi_2_legs.png",
            "breakdown": f"{base}_{tier_key}_multi_3_breakdown.png",
        }
        present = {k: v for k, v in multi_filenames.items() if os.path.exists(os.path.join(CARDS_DIR, v))}
        if present:
            image_names = {}
            for key, fname in present.items():
                dest_name = f"{tier_key}_multi_{key}.png"
                shutil.copyfile(os.path.join(CARDS_DIR, fname), os.path.join(review_dir, dest_name))
                image_names[key] = dest_name
                manifest_files.append(dest_name)
            metadata[f"{tier_key}_multi_carousel_paths"] = [
                os.path.join("data", "review", pick_id, image_names[k]) for k in ("cover", "legs", "breakdown") if k in image_names
            ]
            metadata[f"{tier_key}_multi_carousel_urls"] = [brp.raw_url(repo, present[k]) for k in ("cover", "legs", "breakdown") if k in present]
            intended_platforms.add("instagram_feed")

    _freeze_tier("punter", punter_legs, run_data.get("punter_multi_promo_hint"), brp.build_punter_multi_text, "PUNTER_BET")
    _freeze_tier("gambler", gambler_legs, run_data.get("gambler_multi_promo_hint"), brp.build_gambler_multi_text, "GAMBLER_BET")

    metadata.pop("reasoning", None)  # only relevant for the "neither tier cleared" early-return case above
    metadata["intended_platforms"] = sorted(intended_platforms)

    with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)
    manifest_files.append("post-metadata.json")

    preview_pick_stub = {
        "_telegram_text": tier_texts.get("punter", "") + ("\n\n---\n\n" if len(tier_texts) == 2 else "") + tier_texts.get("gambler", ""),
        "_instagram_caption": "(see per-tier text above — no single Instagram caption for a weekend-multi-only post)",
    }
    image_files = [n for n in manifest_files if n.endswith(".png")]
    preview_html = brp.build_preview_html(preview_pick_stub, metadata, image_files)
    with open(os.path.join(review_dir, "preview.html"), "w") as f:
        f.write(preview_html)
    manifest_files.append("preview.html")

    manifest = build_manifest(review_dir, manifest_files, extra={
        "pick_id": pick_id, "created_at": datetime.now(timezone.utc).isoformat(),
    })
    write_manifest(manifest, os.path.join(review_dir, "manifest.json"))

    print(f"Built weekend multi review package: data/review/{pick_id}/ ({len(manifest_files)} files checksummed)")
    return metadata


if __name__ == "__main__":
    main()
