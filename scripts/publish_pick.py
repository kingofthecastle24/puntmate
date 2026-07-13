#!/usr/bin/env python3
"""
publish_pick.py — the ONLY script that actually posts to Telegram, Instagram
or Facebook. Runs in the "publish" job, after the "production" environment
approval gate, using the exact data/social_post.json produced by the approved
run (downloaded as a workflow artifact — not re-read from main, which could
have moved on if another run started in between).

Honors DRY_RUN=true (the default for manual testing): logs exactly what would
be sent to each platform without calling any API. Real publishing needs
DRY_RUN=false, which generate.yml only sets for schedule-triggered runs or an
explicit manual dry_run=false dispatch.

Also enforces duplicate-publish protection: if data/published/<pick_id>.json
already exists on main, this pick has already gone out — skip everything and
exit 0 rather than posting twice (belt-and-braces alongside the workflow-level
concurrency group).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PUBLISHED_DIR = os.path.join(REPO_ROOT, 'data', 'published')

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")


def already_published(pick_id):
    return os.path.exists(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"))


def mark_published(pick_id, results):
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    with open(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"), 'w') as f:
        json.dump(results, f, indent=2)


def publish(post, results):
    """Live-publish path. Mutates `results` in place with per-platform outcomes."""
    platforms = post.get("intended_platforms", [])

    if "telegram" in platforms:
        try:
            from post_telegram import send_picks_card, post_text
            tip_path = post["carousel_paths"][1] if len(post.get("carousel_paths", [])) > 1 else \
                       (post["carousel_paths"][0] if post.get("carousel_paths") else None)
            if tip_path and os.path.exists(tip_path):
                r = send_picks_card(tip_path, caption=post["telegram_message"])
            else:
                r = post_text(post["telegram_message"])
            results["telegram"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
        except Exception as e:
            results["telegram"] = {"ok": False, "error": str(e)}
            print(f"  ✗ Telegram error: {e}")

    if "instagram_feed" in platforms:
        try:
            from post_instagram import post_carousel_to_instagram
            ok = post_carousel_to_instagram(
                slide_paths=post.get("carousel_paths", []),
                caption=post.get("caption"),
                slide_urls=post.get("carousel_urls"),
            )
            results["instagram_feed"] = {"ok": bool(ok)}
        except Exception as e:
            results["instagram_feed"] = {"ok": False, "error": str(e)}
            print(f"  ✗ Instagram feed error: {e}")

    if "instagram_story" in platforms:
        try:
            from post_instagram_story import post_story_to_instagram
            media_id = post_story_to_instagram(post["story_url"])
            results["instagram_story"] = {"ok": media_id is not None, "media_id": media_id}
        except Exception as e:
            results["instagram_story"] = {"ok": False, "error": str(e)}
            print(f"  ✗ Instagram Story error: {e}")

    if "facebook" in platforms:
        try:
            import requests
            page_id = os.environ.get("FACEBOOK_PAGE_ID", "").strip()
            token = os.environ.get("META_PAGE_TOKEN", "").strip()
            if not page_id or not token:
                results["facebook"] = {"ok": False, "error": "FACEBOOK_PAGE_ID/META_PAGE_TOKEN not set"}
            else:
                image_url = post.get("image_url", "")
                if image_url:
                    resp = requests.post(
                        "https://graph.facebook.com/v19.0/" + page_id + "/photos",
                        data={"url": image_url, "caption": post.get("caption", ""), "access_token": token},
                        timeout=30,
                    )
                else:
                    resp = requests.post(
                        "https://graph.facebook.com/v19.0/" + page_id + "/feed",
                        data={"message": post.get("caption", ""), "access_token": token},
                        timeout=30,
                    )
                result = resp.json()
                results["facebook"] = {"ok": "error" not in result, "detail": result}
        except Exception as e:
            results["facebook"] = {"ok": False, "error": str(e)}
            print(f"  ✗ Facebook error: {e}")

    return results


def dry_run_report(post):
    print("=" * 55)
    print("DRY RUN — no platform will receive a post")
    print("=" * 55)
    for platform in post.get("intended_platforms", []):
        print(f"\n[{platform}]")
        if platform == "telegram":
            print(f"  Would send photo: {post['carousel_paths'][1] if len(post.get('carousel_paths', [])) > 1 else '(text only)'}")
            print(f"  Caption:\n{post['telegram_message'][:400]}")
        elif platform == "instagram_feed":
            print(f"  Would post carousel: {post.get('carousel_urls')}")
            print(f"  Caption:\n{post['caption'][:400]}")
        elif platform == "instagram_story":
            print(f"  Would post Story: {post.get('story_url')}")
        elif platform == "facebook":
            print(f"  Would post: {post.get('image_url')}")
            print(f"  Caption:\n{post['caption'][:400]}")
    print("\n" + "=" * 55)
    print("DRY RUN complete — nothing was actually sent.")
    print("=" * 55)


def main():
    social_post_path = os.environ.get("SOCIAL_POST_PATH", os.path.join(REPO_ROOT, "data", "social_post.json"))
    with open(social_post_path) as f:
        post = json.load(f)

    if not post.get("has_picks"):
        print("No picks in this run — nothing to publish.")
        return

    pick_id = post["pick_id"]

    if already_published(pick_id):
        print(f"::notice::{pick_id} was already published (data/published/{pick_id}.json exists) — skipping to avoid a duplicate post.")
        return

    if DRY_RUN:
        dry_run_report(post)
        return

    print(f"LIVE PUBLISH — pick_id={pick_id}, platforms={post.get('intended_platforms')}")
    results = {"pick_id": pick_id, "platforms": {}}
    publish(post, results["platforms"])

    all_ok = all(r.get("ok") for r in results["platforms"].values()) if results["platforms"] else False
    print("\n" + "=" * 55)
    for platform, r in results["platforms"].items():
        status = "✅" if r.get("ok") else "❌"
        print(f"{status} {platform}: {r}")
    print("=" * 55)

    mark_published(pick_id, results)

    if not all_ok:
        print("::warning::One or more platforms failed — see above. Marked published anyway to avoid re-sending to platforms that DID succeed on a re-run; check logs and post any failed platform manually if needed.")


if __name__ == "__main__":
    main()
