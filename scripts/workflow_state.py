"""
workflow_state.py — named pipeline states + enforced valid transitions.

States: GENERATED, PREVIEW_READY, AWAITING_APPROVAL, APPROVED, REJECTED,
PUBLISHING, PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED.

Persisted per-pick at data/state/<pick_id>.json so any job (or a human
reading the repo) can see the current state and history. The one transition
that must be impossible under any circumstance is REJECTED → PUBLISHED —
that's the exact failure mode the freeze/approval system exists to prevent
(a rejected post must never be able to go out later, e.g. via a stale retry
or a re-run of publish.yml).
"""

import json
import os
from datetime import datetime, timezone

GENERATED = "GENERATED"
PREVIEW_READY = "PREVIEW_READY"
AWAITING_APPROVAL = "AWAITING_APPROVAL"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
PUBLISHING = "PUBLISHING"
PUBLISHED = "PUBLISHED"
PARTIALLY_PUBLISHED = "PARTIALLY_PUBLISHED"
PUBLISH_FAILED = "PUBLISH_FAILED"

ALL_STATES = {
    GENERATED, PREVIEW_READY, AWAITING_APPROVAL, APPROVED, REJECTED,
    PUBLISHING, PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED,
}

# Explicit allow-list of forward transitions. Anything not listed here is
# invalid, including (most importantly) REJECTED -> PUBLISHED and any
# transition out of a terminal state.
VALID_TRANSITIONS = {
    GENERATED: {PREVIEW_READY},
    PREVIEW_READY: {AWAITING_APPROVAL},
    AWAITING_APPROVAL: {APPROVED, REJECTED},
    APPROVED: {PUBLISHING},
    REJECTED: set(),                # terminal — nothing may follow a rejection
    PUBLISHING: {PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED},
    PUBLISHED: set(),                # terminal
    PARTIALLY_PUBLISHED: set(),      # terminal (a manual re-publish would be a new pick_id/run)
    PUBLISH_FAILED: set(),           # terminal
}


class InvalidTransitionError(ValueError):
    pass


def _state_path(repo_root, pick_id):
    return os.path.join(repo_root, "data", "state", f"{pick_id}.json")


def load_state(repo_root, pick_id):
    path = _state_path(repo_root, pick_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def transition(repo_root, pick_id, new_state, note=None):
    """Validates and persists a state transition. Raises InvalidTransitionError
    if the transition isn't allowed (including transitioning a pick_id that
    doesn't exist yet into anything other than GENERATED)."""
    if new_state not in ALL_STATES:
        raise InvalidTransitionError(f"unknown state: {new_state}")

    current = load_state(repo_root, pick_id)
    current_state = current["state"] if current else None

    if current_state is None:
        if new_state != GENERATED:
            raise InvalidTransitionError(
                f"pick {pick_id} has no state yet — first transition must be GENERATED, got {new_state}"
            )
        allowed = True
    else:
        allowed = new_state in VALID_TRANSITIONS.get(current_state, set())

    if not allowed:
        raise InvalidTransitionError(
            f"invalid transition for {pick_id}: {current_state} -> {new_state}"
        )

    history = (current or {}).get("history", [])
    history.append({
        "state": new_state,
        "at": datetime.now(timezone.utc).isoformat(),
        "note": note,
    })
    record = {"pick_id": pick_id, "state": new_state, "history": history}

    path = _state_path(repo_root, pick_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return record
