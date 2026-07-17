#!/usr/bin/env python3
"""
publish_pick.py — the ONLY script that actually posts to Telegram or
Instagram. Runs in the "publish" job, after the "production" environment
approval gate, using the EXACT frozen files from data/review/<pick_id>/
(downloaded as this run's artifact) — never regenerated, never re-read from
whatever's newest on main.

Facebook is NOT posted to directly. Facebook's Page access token lost the
publish_actions permission (Meta deprecated it) — this was confirmed by a
real failed live post (see data/published/2026-07-14_France_vs_Spain.json:
"(#200) The permission(s) publish_actions are not available... deprecated").
Since the Facebook Page is already linked to the Instagram account, Facebook
is reported as "expected via linked Instagram account" — never claimed as a
verified success, because it isn't independently verifiable from here.

Freeze/verify: before publishing anything, this reloads manifest.json and
re-hashes every file it lists. A single mismatch aborts the ENTIRE publish
(nothing goes out on any platform) and requires a fresh approval — see
manifest.py.

Platforms publish independently: if Telegram succeeds and Instagram fails
(or vice versa), the successful post stays live and is reported as such —
one platform's failure never rolls back another's success.

Telegram approval note: per Micah, Telegram is deliberately behind the SAME
single "production" environment gate as Instagram/Facebook for now (phase 1
— prove the whole pipeline out with him as the approver on every platform).
`intended_platforms` is a plain list on post-metadata.json and every platform
here is published from the same single approval; if/when per-platform gating
is wanted later (e.g. Telegram auto-publishes once trusted), that's a matter
of splitting `intended_platforms` handling or adding a second gated job — a
config/workflow change, not a rewrite of this script.

Honors DRY_RUN=true (the default): logs exactly what would be sent to each
platform without calling any API.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from manifest import load_manifest, verify_manifest
from workflow_state import transition, APPROVED, PUBLISHING, PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED
import email_service

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")
PUBLISHED_DIR = os.path.join(REPO_ROOT, "data", "published")

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")


def already_published(pick_id):
    return os.path.exists(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"))


def mark_published(pick_id, results):
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    with open(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"), "w") as f:
        json.dump(results, f, indent=2)


def publish(review_dir, metadata, telegram_text, instagram_caption, results):
    """Live-publish path. Each platform is independent — one failing must not
    stop or roll back another."""
    platforms = metadata.get("intended_platforms", [])

    if "telegram" in platforms:
        try:
            from post_telegram import send_picks_card, post_text
            tip_path = os.path.join(review_dir, "tip.png")
            if os.path.exists(tip_path):
                r = send_picks_card(tip_path, caption=telegram_text)
            else:
                r = post_text(telegram_text)
            results["telegram"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
        except Exception as e:
            results["telegram"] = {"ok": False, "error": str(e)}
            print(f"  Telegram error: {e}")

    if "instagram_feed" in platforms:
        try:
            from post_instagram import post_carousel_to_instagram
            ok = post_carousel_to_instagram(
                slide_paths=[os.path.join(review_dir, n) for n in ("cover.png", "tip.png", "breakdown.png") if os.path.exists(os.path.join(review_dir, n))],
                caption=instagram_caption,
                slide_urls=metadata.get("carousel_urls"),
            )
            results["instagram_feed"] = {"ok": bool(ok)}
        except Exception as e:
            results["instagram_feed"] = {"ok": False, "error": str(e)}
            print(f"  Instagram feed error: {e}")

    if "instagram_story" in platforms:
        try:
            from post_instagram_story import post_story_to_instagram
            media_id = post_story_to_instagram(metadata.get("story_url"))
            results["instagram_story"] = {"ok": media_id is not None, "media_id": media_id}
        except Exception as e:
            results["instagram_story"] = {"ok": False, "error": str(e)}
            print(f"  Instagram Story error: {e}")

    if "facebook" in platforms:
        # Deliberately NOT calling the Graph API directly — see module docstring.
        results["facebook"] = {
            "status": "via_linked_instagram",
            "note": "Facebook: expected via linked Instagram account (direct Page posting is disabled — publish_actions permission is deprecated).",
        }

    return results


def dry_run_report(metadata, telegram_text, instagram_caption):
    print("=" * 55)
    print("DRY RUN — no platform will receive a post")
    print("=" * 55)
    for platform in metadata.get("intended_platforms", []):
        print(f"\n[{platform}]")
        if platform == "telegram":
            print(f"  Caption:\n{telegram_text[:400]}")
        elif platform == "instagram_feed":
            print(f"  Would post carousel: {metadata.get('carousel_urls')}")
            print(f"  Caption:\n{instagram_caption[:400]}")
        elif platform == "instagram_story":
            print(f"  Would post Story: {metadata.get('story_url')}")
        elif platform == "facebook":
            print("  Facebook: expected via linked Instagram account (no direct post attempted).")
    print("\n" + "=" * 55)
    print("DRY RUN complete — nothing was actually sent.")
    print("=" * 55)


def main():
    review_dir = os.environ.get("REVIEW_DIR")
    if not review_dir:
        pick_id = os.environ.get("PICK_ID", "")
        review_dir = os.path.join(REVIEW_ROOT, pick_id)

    meta_path = os.path.join(review_dir, "post-metadata.json")
    if not os.path.exists(meta_path):
        print("No post-metadata.json found — nothing to publish.")
        return

    with open(meta_path) as f:
        metadata = json.load(f)

    if not metadata.get("has_pick"):
        print("NO_BET — nothing to publish.")
        return

    pick_id = metadata["pick_id"]

    if already_published(pick_id):
        print(f"::notice::{pick_id} was already published — skipping to avoid a duplicate post.")
        return

    with open(os.path.join(review_dir, "telegram-post.txt")) as f:
        telegram_text = f.read()
    with open(os.path.join(review_dir, "instagram-caption.txt")) as f:
        instagram_caption = f.read()

    if DRY_RUN:
        # Dry runs (manual testing) don't move workflow state at all — only a
        # real approved run does.
        manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
        verify_manifest(manifest, review_dir)  # surfaced in the report either way
        dry_run_report(metadata, telegram_text, instagram_caption)
        return

    # This script only ever runs after the GitHub environment approval gate
    # passed, so AWAITING_APPROVAL -> APPROVED is safe here. Checksum
    # verification happens INSIDE the PUBLISHING state — a mismatch is a
    # publish-time failure (PUBLISHING -> PUBLISH_FAILED), not a rejection.
    auto_mode = os.environ.get("AUTO_PUBLISH", "").strip().lower() == "true"
    approval_note = (
        "AUTO-PUBLISH TRIAL — no human gate; copy validator (hard-fail at freeze) was the only gate"
        if auto_mode else "approval confirmed, entering publish"
    )
    transition(REPO_ROOT, pick_id, APPROVED, note=approval_note)
    transition(REPO_ROOT, pick_id, PUBLISHING)

    # ── Freeze verification — the whole point of the manifest system ──────
    manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
    ok, mismatches = verify_manifest(manifest, review_dir)
    if not ok:
        print("::error::Checksum mismatch — one or more frozen files changed since approval. REFUSING to publish.")
        for m in mismatches:
            print(f"  - {m}")
        transition(REPO_ROOT, pick_id, PUBLISH_FAILED, note="checksum mismatch, publish blocked")
        email_service.send_result_email(metadata, {"error": "checksum mismatch — publish blocked, see run logs"}, "PUBLISH_FAILED")
        sys.exit(1)

    print(f"LIVE PUBLISH — pick_id={pick_id}, platforms={metadata.get('intended_platforms')}")
    results = {}
    publish(review_dir, metadata, telegram_text, instagram_caption, results)

    def _platform_ok(r):
        return r.get("ok") is True or r.get("status") == "via_linked_instagram"

    real_platforms = [p for p in results if p != "facebook"]
    all_ok = all(results[p].get("ok") for p in real_platforms) if real_platforms else False
    any_ok = any(results[p].get("ok") for p in real_platforms) if real_platforms else False

    print("\n" + "=" * 55)
    for platform, r in results.items():
        status = "OK" if _platform_ok(r) else "FAILED"
        print(f"[{status}] {platform}: {r}")
    print("=" * 55)

    mark_published(pick_id, results)

    if all_ok:
        final_state = PUBLISHED
    elif any_ok:
        final_state = PARTIALLY_PUBLISHED
    else:
        final_state = PUBLISH_FAILED
    transition(REPO_ROOT, pick_id, final_state, note=json.dumps({k: v.get("ok", v.get("status")) for k, v in results.items()}))

    metadata["_telegram_text"] = telegram_text
    metadata["_instagram_caption"] = instagram_caption
    email_service.send_result_email(metadata, results, final_state)

    if final_state != PUBLISHED:
        print(f"::warning::Publish ended in state {final_state} — see results above.")


if __name__ == "__main__":
    main()
