#!/usr/bin/env python3
"""
handle_rejection.py — runs when the GitHub environment approval step is
rejected (or the run is cancelled at that gate) instead of approved.

Records workflow state REJECTED (a terminal state — workflow_state.py's
transition table has no outgoing edges from REJECTED, so any later attempt
to publish this pick_id, from any workflow or retry, is rejected in code,
not just in intent), retains the review package exactly as it was (nothing
is deleted), and sends the rejection email.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from workflow_state import transition, REJECTED
import email_service

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")


def main():
    pick_id = os.environ.get("PICK_ID", "").strip()
    if not pick_id:
        print("No pick_id — nothing to mark as rejected.")
        return

    meta_path = os.path.join(REVIEW_ROOT, pick_id, "post-metadata.json")
    with open(meta_path) as f:
        metadata = json.load(f)

    transition(REPO_ROOT, pick_id, REJECTED, note="GitHub environment approval rejected/cancelled")
    email_service.send_rejection_email(metadata)
    print(f"{pick_id} recorded as REJECTED. Nothing was published. Review package retained at data/review/{pick_id}/.")


if __name__ == "__main__":
    main()
