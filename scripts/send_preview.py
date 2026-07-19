#!/usr/bin/env python3
"""
send_preview.py — runs at the end of the "generate" job, after
build_review_package.py has frozen everything. Transitions workflow state
GENERATED -> PREVIEW_READY -> AWAITING_APPROVAL and sends the Gmail preview
email (or the No-Bet notice). This is the last thing that happens before the
GitHub environment approval gate.

If Gmail isn't configured, email_service already logs a clear warning and
returns False — this script does NOT fail the run in that case, because the
job summary + preview.html + uploaded artifact are an equally complete
review surface (per spec: "Gmail preview failure must not allow blind
approval unless Dispatch/GitHub has an equally complete visual preview" —
that's exactly what the job summary table + preview.html give Micah).

Incident note (run #51, 2026-07-18): a same-day re-run selected the same
fixture an earlier run that day had already carried to a live pick_id
(same date + same slugified match = same pick_id, since live pick_ids have
no per-run suffix). transition(pick_id, GENERATED) is only valid when a
pick_id has NO existing state, so this raised workflow_state.
InvalidTransitionError, uncaught, and crashed the whole generate job with
exit code 1 — which then cascaded into the publish job failing too (it
tried to download a review artifact that was never produced). The primary
fix is upstream in main.py (never select an already-actioned fixture again
today), but every transition() call here is now also wrapped so a
collision degrades to a loud warning + graceful no-op instead of an
uncaught crash, in case the upstream guard is ever bypassed (force_test_pick,
a future manual dispatch race, etc).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from workflow_state import transition, InvalidTransitionError, GENERATED, PREVIEW_READY, AWAITING_APPROVAL
import email_service

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")


def approval_url():
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""


def _safe_transition(pick_id, new_state, note=None):
    """transition() but a collision (pick_id already actioned earlier today)
    degrades to a warning instead of an uncaught crash. Returns True if the
    transition succeeded, False if it was skipped due to a collision."""
    try:
        transition(REPO_ROOT, pick_id, new_state, note=note)
        return True
    except InvalidTransitionError as e:
        print(f"::warning::Skipping duplicate pipeline state for {pick_id}: {e}. "
              f"This fixture already has a state recorded today — not re-entering "
              f"the approval gate or resending a preview for it.")
        return False


def main():
    pick_id = os.environ.get("PICK_ID", "").strip()
    if not pick_id:
        print("No pick_id provided (NO_BET or no matches today) — nothing to preview.")
        return

    review_dir = os.path.join(REVIEW_ROOT, pick_id)
    meta_path = os.path.join(review_dir, "post-metadata.json")
    with open(meta_path) as f:
        metadata = json.load(f)

    if not _safe_transition(pick_id, GENERATED, note="review package built"):
        return

    # 2026-07-19: a weekend multi post (is_weekend_multi) has has_pick=False
    # (no single featured selection) but IS a real public post if either
    # tier cleared the bar -- it needs the SAME approval gate as any other
    # post, just its own preview email shape (no single telegram-post.txt/
    # instagram-caption.txt to show).
    if metadata.get("is_weekend_multi"):
        if not (metadata.get("has_punter_multi") or metadata.get("has_gambler_multi")):
            if not _safe_transition(pick_id, PREVIEW_READY, note="weekend multi: neither tier cleared the bar"):
                return
            print(f"Weekend multi — neither tier cleared 3 legs this weekend, nothing to approve for {pick_id}.")
            return
        if not _safe_transition(pick_id, PREVIEW_READY, note="weekend multi review package frozen"):
            return
        if not _safe_transition(pick_id, AWAITING_APPROVAL, note="weekend multi entering GitHub environment approval gate"):
            return

        def _read_if_exists(name):
            path = os.path.join(review_dir, name)
            if not os.path.exists(path):
                return ""
            with open(path) as f:
                return f.read()

        punter_text = _read_if_exists("punter-multi-post.txt")
        gambler_text = _read_if_exists("gambler-multi-post.txt")
        image_paths = [
            os.path.join(review_dir, name) for name in os.listdir(review_dir)
            if name.endswith(".png")
        ]
        email_service.send_weekend_multi_email(metadata, image_paths, punter_text, gambler_text, approval_url())
        print(f"Weekend multi — preview sent, awaiting approval gate for {pick_id}.")
        return

    if not metadata.get("has_pick"):
        if metadata.get("has_watchlist"):
            # Phase 4: a No-Bet day WITH a watchlist post goes through the
            # same gate as a real pick (human approval, or the auto-publish
            # trial when enabled) — it's still a public post.
            if not _safe_transition(pick_id, PREVIEW_READY, note="no_bet + watchlist post frozen"):
                return
            if not _safe_transition(pick_id, AWAITING_APPROVAL, note="watchlist post entering approval gate"):
                return
            email_service.send_no_bet_email(metadata)
            print(f"NO_BET + watchlist — post frozen and awaiting gate for {pick_id}.")
        else:
            if not _safe_transition(pick_id, PREVIEW_READY, note="no_bet"):
                return
            email_service.send_no_bet_email(metadata)
            print(f"NO_BET — notice sent, no approval gate entered for {pick_id}.")
        return

    if not _safe_transition(pick_id, PREVIEW_READY, note="review package frozen"):
        return
    if not _safe_transition(pick_id, AWAITING_APPROVAL, note="entering GitHub environment approval gate"):
        return

    with open(os.path.join(review_dir, "telegram-post.txt")) as f:
        telegram_text = f.read()
    with open(os.path.join(review_dir, "instagram-caption.txt")) as f:
        instagram_caption = f.read()

    image_paths = [
        os.path.join(review_dir, name) for name in ("cover.png", "tip.png", "breakdown.png", "story.png")
        if os.path.exists(os.path.join(review_dir, name))
    ]

    email_service.send_preview_email(metadata, image_paths, telegram_text, instagram_caption, approval_url())


if __name__ == "__main__":
    main()
