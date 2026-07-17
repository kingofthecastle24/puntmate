#!/usr/bin/env python3
"""
publish_watchlist.py — Phase 4. Publishes the frozen No-Bet-day Watchlist
post (Telegram text only — no images, no odds, no selections).

Mirrors publish_pick.py's guarantees at a smaller scale:
  - only publishes the exact frozen watchlist-post.txt, verified against
    manifest.json checksums (refuses on any mismatch)
  - honors DRY_RUN (logs what would be sent, touches nothing)
  - drives the same workflow_state machine (AWAITING_APPROVAL -> APPROVED ->
    PUBLISHING -> PUBLISHED/PUBLISH_FAILED), with an explicit AUTO-PUBLISH
    TRIAL note when no human gate was involved
  - records data/published/<pick_id>.json so a re-run can never double-post
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from manifest import load_manifest, verify_manifest
from workflow_state import transition, APPROVED, PUBLISHING, PUBLISHED, PUBLISH_FAILED

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


def main():
    pick_id = os.environ.get("PICK_ID", "").strip()
    if not pick_id:
        print("No PICK_ID — nothing to publish.")
        return

    review_dir = os.path.join(REVIEW_ROOT, pick_id)
    meta_path = os.path.join(review_dir, "post-metadata.json")
    with open(meta_path) as f:
        metadata = json.load(f)

    if not metadata.get("has_watchlist"):
        print("No watchlist in this review package — nothing to publish.")
        return

    if already_published(pick_id):
        print(f"::notice::{pick_id} already published — skipping to avoid a duplicate post.")
        return

    with open(os.path.join(review_dir, "watchlist-post.txt")) as f:
        watchlist_text = f.read()

    manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
    ok, mismatches = verify_manifest(manifest, review_dir)
    if not ok:
        print("::error::Checksum mismatch on frozen watchlist post — REFUSING to publish.")
        for m in mismatches:
            print(f"  - {m}")
        if not DRY_RUN:
            transition(REPO_ROOT, pick_id, APPROVED, note="gate passed but freeze verification failed")
            transition(REPO_ROOT, pick_id, PUBLISHING)
            transition(REPO_ROOT, pick_id, PUBLISH_FAILED, note="checksum mismatch, watchlist publish blocked")
        sys.exit(1)

    if DRY_RUN:
        print("DRY RUN — watchlist post that WOULD be sent to Telegram:")
        print("-" * 55)
        print(watchlist_text)
        print("-" * 55)
        return

    auto_mode = os.environ.get("AUTO_PUBLISH", "").strip().lower() == "true"
    approval_note = (
        "AUTO-PUBLISH TRIAL — no human gate; copy validator (hard-fail at freeze) was the only gate"
        if auto_mode else "approval confirmed, entering publish"
    )
    transition(REPO_ROOT, pick_id, APPROVED, note=approval_note)
    transition(REPO_ROOT, pick_id, PUBLISHING)

    results = {}
    try:
        from post_telegram import post_text
        r = post_text(watchlist_text)
        results["telegram"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
    except Exception as e:
        results["telegram"] = {"ok": False, "error": str(e)}
        print(f"  Telegram error: {e}")

    mark_published(pick_id, results)
    final = PUBLISHED if results.get("telegram", {}).get("ok") else PUBLISH_FAILED
    transition(REPO_ROOT, pick_id, final, note=json.dumps({k: v.get("ok") for k, v in results.items()}))
    print(f"Watchlist publish complete: {final} — {results}")
    if final == PUBLISH_FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
