#!/usr/bin/env python3
"""
build_review_package.py — builds the frozen review package for one pick,
after generate_pick.py has produced a verdict and render_brand_templates.py
has rendered the cards (or after a NO_BET verdict, in which case no cards
exist and no publish step will ever run for this pick_id).

pick_id namespace: dry-run runs (DRY_RUN=true, the workflow_dispatch default)
get a "_dryrun" suffix appended to pick_id, e.g.
"2026-07-17_Sydney_Roosters_vs_Melbourne_Storm_dryrun". This keeps manual
testing/preview runs in their own workflow_state.py + data/review/ namespace
so they can never collide with — or terminally block — a same-day live
(DRY_RUN=false) run on the same fixture. Before this, pick_id was date+match
only, so a dry-run test parked a match's pick_id at AWAITING_APPROVAL (or
later REJECTED/PUBLISHED) for the rest of that day, and any subsequent real
run on the same match hard-failed with workflow_state.InvalidTransitionError.
Live pick_ids are unchanged (no suffix) — this is purely additive.

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
from copy_validator import validate_post, validate_text, CopyValidationError

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
LATEST_RUN_PATH = os.path.join(REPO_ROOT, "data", "latest_run.json")
CARDS_DIR = os.path.join(REPO_ROOT, "data", "cards")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")

RESPONSIBLE_LINE = "Problem Gambling Foundation NZ: 0800 664 262"

# Same parsing convention as publish_pick.py's DRY_RUN, so "true"/"false"
# (the workflow_dispatch input's literal string form) and unset (defaults to
# dry-run, the safer assumption for local/manual invocation) both behave
# correctly.
DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")


def _pick_id_suffix(dry_run=None):
    """The pick_id namespace suffix for the given dry-run mode (module-level
    DRY_RUN if not overridden). See module docstring for why this exists."""
    return "_dryrun" if (DRY_RUN if dry_run is None else dry_run) else ""


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
    # Micah, 2026-07-18: dropped the "Keep this one light..." risk-tier
    # caution line from public copy -- didn't like the tone/placement.
    # public_caution is still computed and kept in post-metadata.json
    # (internal reference only) but no longer surfaces in the actual post.
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
    # Same removal as build_telegram_text — see note there.
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


def _fmt_kickoff_nzt(iso_ts):
    """Best-effort kickoff formatting in NZT; falls back to raw string."""
    try:
        from datetime import datetime, timedelta
        dt = datetime.fromisoformat(str(iso_ts).replace("Z", "+00:00"))
        nzt = dt + timedelta(hours=12)  # NZST; close enough for a watchlist line year-round
        return nzt.strftime("%a %I:%M%p NZT").replace(" 0", " ")
    except Exception:
        return str(iso_ts)


def build_watchlist_text(watchlist, post_date):
    """Phase 4 — the public Telegram text for a No-Bet-day Watchlist post.
    Deliberately: no selections, no odds, no anything framed as advice. The
    honest message IS the product: nothing cleared the bar today."""
    lines = [
        "*🔍 PUNTMATE NZ — NO BET TODAY*",
        "",
        "_Nothing cleared the bar today — no pick meets my criteria, so we're sitting this one out. "
        "A no-bet day protects the strike rate; forcing a pick never does._",
        "",
        "*On the watchlist today:*",
    ]
    for w in watchlist:
        lines.append(f"• {w.get('sport_label','')}: {w.get('match','')} — {_fmt_kickoff_nzt(w.get('kickoff',''))}")
    lines += [
        "",
        "Back tomorrow with the numbers.",
        "",
        "──────────────────",
        "📲 Join Telegram for daily picks",
        f"R18 · Gamble responsibly · {RESPONSIBLE_LINE}",
    ]
    return "\n".join(lines)


def build_multi_text(pick):
    """Phase 5 — rare Gambler-tier multi as a SECONDARY Telegram post.
    Only called when generate_pick produced 3 genuine, independently
    defensible legs on distinct matches (see multi_legs logic there)."""
    legs = pick["multi_legs"]
    combined = 1.0
    for leg in legs:
        combined *= float(leg["odds"])
    lines = [
        "*🎰 PUNTMATE NZ — THE MULTI*",
        "",
        "_Rare one: today produced three selections that each stand on their own. "
        "Rolled together as a multi they pay big — but every leg has to land, "
        "so treat this strictly as a Gambler-tier swing, not the day's real pick "
        "(that's the post above)._",
        "",
    ]
    for i, leg in enumerate(legs, 1):
        lines.append(f"*Leg {i}:* {leg['match']} — {leg['selection']} @ {leg['odds']} ({leg['market']})")
    lines += [
        "",
        f"*Combined: {combined:.2f}*",
        "*BET TYPE: GAMBLER*",
        "",
        "One leg fails, the lot fails. Small stakes territory.",
        "",
        "──────────────────",
        f"R18 · Gamble responsibly · {RESPONSIBLE_LINE}",
    ]
    return "\n".join(lines)


def build_no_bet_metadata(reasoning, research_warnings, run_id, post_date, dry_run=None):
    return {
        "has_pick": False,
        "pick_id": f"{post_date}_no-bet{_pick_id_suffix(dry_run)}",
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
        metadata = build_no_bet_metadata(reasoning, warnings, run_id, post_date, DRY_RUN)
        review_dir = os.path.join(REVIEW_ROOT, metadata["pick_id"])
        os.makedirs(review_dir, exist_ok=True)

        # Phase 4: watchlist post on genuine No-Bet days (main.py only writes
        # a watchlist when fixtures existed but nothing cleared the bar).
        watchlist = run_data.get("watchlist") or []
        manifest_files = ["post-metadata.json"]
        if watchlist:
            watchlist_text = build_watchlist_text(watchlist, post_date)
            # Same hard validation gate as real picks. risk=NO_BET so the
            # no-bet phrasing is allowed; internal-leak + tone checks apply.
            validate_text(watchlist_text, risk="NO_BET", public=True)
            with open(os.path.join(review_dir, "watchlist-post.txt"), "w") as f:
                f.write(watchlist_text)
            metadata["has_watchlist"] = True
            metadata["watchlist"] = watchlist
            metadata["intended_platforms"] = ["telegram"]
            manifest_files.append("watchlist-post.txt")

        with open(os.path.join(review_dir, "post-metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        manifest = build_manifest(review_dir, manifest_files, extra={
            "pick_id": metadata["pick_id"],
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        write_manifest(manifest, os.path.join(review_dir, "manifest.json"))
        if watchlist:
            print(f"NO_BET today — built watchlist post ({len(watchlist)} fixtures) at {metadata['pick_id']}/ (goes through the same gate).")
        else:
            print(f"NO_BET today — wrote {metadata['pick_id']}/post-metadata.json (no fixtures at all; staying silent).")
        return metadata

    repo = os.environ.get("GITHUB_REPOSITORY", "kingofthecastle24/puntmate")
    theme = choose_theme(pick)
    match_slug = slugify(pick["match"])
    base = f"{post_date}_{match_slug}_{theme}"
    pick_id = f"{post_date}_{match_slug}{_pick_id_suffix()}"

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

    # Phase 5: rare Gambler-tier multi (secondary Telegram post). Frozen and
    # checksummed with everything else; validated under GAMBLER_BET rules so
    # chasing/guarantee language can never ship. Computed BEFORE
    # post-metadata.json/preview.html are written (bug fixed 2026-07-18:
    # this used to run AFTER those writes, so has_multi/multi_promo_hint
    # never actually reached the frozen metadata, the Gmail preview, or the
    # job summary -- Micah would never have seen "there's a multi attached"
    # anywhere except by noticing the extra file in the artifact).
    multi_manifest_extra = []
    if len(pick.get("multi_legs") or []) >= 3:
        multi_text = build_multi_text(pick)
        validate_text(multi_text, risk=pick["risk"], bet_type="GAMBLER_BET", public=True)
        with open(os.path.join(review_dir, "multi-post.txt"), "w") as f:
            f.write(multi_text)
        multi_manifest_extra.append("multi-post.txt")
        metadata["has_multi"] = True
        if pick.get("multi_promo_hint"):
            # Internal-only reference for Micah/the Gmail preview -- e.g.
            # "all 4 legs are MLB, TAB's US-sports 4+ leg promo may apply,
            # check current T&Cs". Never written into multi-post.txt itself.
            metadata["multi_promo_hint"] = pick["multi_promo_hint"]

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
    manifest_files = ["telegram-post.txt", "instagram-caption.txt", "post-metadata.json", "preview.html"] + list(review_image_names.values()) + multi_manifest_extra
    manifest = build_manifest(review_dir, manifest_files, extra={
        "pick_id": pick_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    write_manifest(manifest, os.path.join(review_dir, "manifest.json"))

    print(f"Built review package: data/review/{pick_id}/ ({len(manifest_files)} files checksummed)")
    return metadata


if __name__ == "__main__":
    main()
