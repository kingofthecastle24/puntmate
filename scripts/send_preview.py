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
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from workflow_state import transition, GENERATED, PREVIEW_READY, AWAITING_APPROVAL
import email_service

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")


def approval_url():
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    return f"{server}/{repo}/actions/runs/{run_id}" if repo and run_id else ""


def main():
    pick_id = os.environ.get("PICK_ID", "").strip()
    if not pick_id:
        print("No pick_id provided (NO_BET or no matches today) — nothing to preview.")
        return

    review_dir = os.path.join(REVIEW_ROOT, pick_id)
    meta_path = os.path.join(review_dir, "post-metadata.json")
    with open(meta_path) as f:
        metadata = json.load(f)

    transition(REPO_ROOT, pick_id, GENERATED, note="review package built")

    if not metadata.get("has_pick"):
        transition(REPO_ROOT, pick_id, PREVIEW_READY, note="no_bet")
        email_service.send_no_bet_email(metadata)
        print(f"NO_BET — notice sent, no approval gate entered for {pick_id}.")
        return

    transition(REPO_ROOT, pick_id, PREVIEW_READY, note="review package frozen")
    transition(REPO_ROOT, pick_id, AWAITING_APPROVAL, note="entering GitHub environment approval gate")

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
