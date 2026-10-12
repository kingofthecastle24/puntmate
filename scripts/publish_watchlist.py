#!/usr/bin/env python3
"""
publish_watchlist.py — Phase 4. Publishes the frozen No-Bet-day Watchlist
post (Telegram text only — no images, no odds, no selections) AND, when
present, the Degen Watch post (2026-10-11, Micah) — the candidate closest
to clearing today's value bar, explicitly unofficial, to Telegram (text)
and Instagram (card), independently of the Watchlist above.

Mirrors publish_pick.py's guarantees at a smaller scale:
  - only publishes the exact frozen watchlist-post.txt / degen-watch-post.txt
    / degen-watch.png, verified against manifest.json checksums (refuses
    on any mismatch)
  - honors DRY_RUN (logs what would be sent, touches nothing)
  - drives the same workflow_state machine (AWAITING_APPROVAL -> APPROVED ->
    PUBLISHING -> PUBLISHED/PARTIALLY_PUBLISHED/PUBLISH_FAILED), with an
    explicit AUTO-PUBLISH TRIAL note when no human gate was involved
  - records data/published/<pick_id>.json so a re-run can never double-post
  - the Watchlist and Degen Watch are independent: Instagram failing (or
    not being configured) never blocks the Watchlist's Telegram post, and
    vice versa — same one-platform-failing-never-blocks-another guarantee
    publish_pick.py already gives the real daily pick.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from manifest import load_manifest, verify_manifest
from workflow_state import transition, APPROVED, PUBLISHING, PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED

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

    has_watchlist = metadata.get("has_watchlist", False)
    has_degen_watch = metadata.get("has_degen_watch", False)
    if not has_watchlist and not has_degen_watch:
        print("No watchlist or Degen Watch in this review package — nothing to publish.")
        return

    if already_published(pick_id):
        print(f"::notice::{pick_id} already published — skipping to avoid a duplicate post.")
        return

    watchlist_text = None
    if has_watchlist:
        with open(os.path.join(review_dir, "watchlist-post.txt")) as f:
            watchlist_text = f.read()

    degen_text = None
    degen_card_path = None
    if has_degen_watch:
        with open(os.path.join(review_dir, "degen-watch-post.txt")) as f:
            degen_text = f.read()
        candidate_path = os.path.join(review_dir, "degen-watch.png")
        if os.path.exists(candidate_path):
            degen_card_path = candidate_path

    manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
    ok, mismatches = verify_manifest(manifest, review_dir)
    if not ok:
        print("::error::Checksum mismatch on frozen watchlist/Degen Watch post — REFUSING to publish.")
        for m in mismatches:
            print(f"  - {m}")
        if not DRY_RUN:
            transition(REPO_ROOT, pick_id, APPROVED, note="gate passed but freeze verification failed")
            transition(REPO_ROOT, pick_id, PUBLISHING)
            transition(REPO_ROOT, pick_id, PUBLISH_FAILED, note="checksum mismatch, watchlist/Degen Watch publish blocked")
        sys.exit(1)

    if DRY_RUN:
        if watchlist_text:
            print("DRY RUN — watchlist post that WOULD be sent to Telegram:")
            print("-" * 55)
            print(watchlist_text)
            print("-" * 55)
        if degen_text:
            print("DRY RUN — Degen Watch post that WOULD be sent to Telegram:")
            print("-" * 55)
            print(degen_text)
            print("-" * 55)
            print(f"DRY RUN — Degen Watch card that WOULD be posted to Instagram: {degen_card_path or '(not rendered — Telegram only)'}")
        return

    auto_mode = os.environ.get("AUTO_PUBLISH", "").strip().lower() == "true"
    approval_note = (
        "AUTO-PUBLISH TRIAL — no human gate; copy validator (hard-fail at freeze) was the only gate"
        if auto_mode else "approval confirmed, entering publish"
    )
    transition(REPO_ROOT, pick_id, APPROVED, note=approval_note)
    transition(REPO_ROOT, pick_id, PUBLISHING)

    results = {}
    if watchlist_text:
        try:
            from post_telegram import post_text
            r = post_text(watchlist_text)
            results["telegram_watchlist"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
        except Exception as e:
            results["telegram_watchlist"] = {"ok": False, "error": str(e)}
            print(f"  Telegram (watchlist) error: {e}")

    if degen_text:
        try:
            from post_telegram import post_text
            r = post_text(degen_text)
            results["telegram_degen_watch"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
        except Exception as e:
            results["telegram_degen_watch"] = {"ok": False, "error": str(e)}
            print(f"  Telegram (Degen Watch) error: {e}")

        if degen_card_path:
            try:
                from post_instagram import post_degen_watch_to_instagram, LAST_ERROR
                ok_ig = post_degen_watch_to_instagram(degen_card_path, degen_text)
                results["instagram_degen_watch"] = {"ok": bool(ok_ig), "error": None if ok_ig else LAST_ERROR}
            except Exception as e:
                results["instagram_degen_watch"] = {"ok": False, "error": str(e)}
                print(f"  Instagram (Degen Watch) error: {e}")
        else:
            results["instagram_degen_watch"] = {"ok": True, "skipped": True, "reason": "card not rendered"}

    mark_published(pick_id, results)

    # Same PUBLISHED/PARTIALLY_PUBLISHED/PUBLISH_FAILED visibility as
    # publish_pick.py — skipped entries (e.g. Instagram never configured,
    # or the Degen Watch card not rendered) don't count against "all ok".
    real_results = [r for r in results.values() if not r.get("skipped")]
    all_ok = all(r.get("ok") for r in real_results) if real_results else False
    any_ok = any(r.get("ok") for r in real_results) if real_results else False
    final = PUBLISHED if all_ok else (PARTIALLY_PUBLISHED if any_ok else PUBLISH_FAILED)
    transition(REPO_ROOT, pick_id, final, note=json.dumps({k: v.get("ok", v.get("skipped")) for k, v in results.items()}))
    print(f"Watchlist/Degen Watch publish complete: {final} — {results}")
    if final == PARTIALLY_PUBLISHED:
        print(f"::warning::Publish ended in state {final} — see results above.")
    elif final == PUBLISH_FAILED:
        sys.exit(1)


if __name__ == "__main__":
    main()
