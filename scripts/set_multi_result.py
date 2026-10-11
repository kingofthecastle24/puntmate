#!/usr/bin/env python3
"""
set_multi_result.py -- record how a published weekend multi finished.

Multis are not in the picks ledger, so check_results.py never settles them.
This writes the outcome to data/multi_results.json (the public record of the
multi) so the owner DM's month figures can include its return.

Usage:
    python scripts/set_multi_result.py <pick_id> <tier> <win|loss|void>

Example:
    python scripts/set_multi_result.py 2026-10-01_weekend_multi punter loss
"""

import json
import os
import sys

PATH = os.path.join(os.path.dirname(__file__), "..", "data", "multi_results.json")
TIERS = ("punter", "gambler", "degenerate")
RESULTS = ("win", "loss", "void")


def set_result(pick_id, tier, result, path=PATH):
    tier, result = tier.lower(), result.lower()
    if tier not in TIERS:
        raise ValueError(f"tier must be one of {TIERS}")
    if result not in RESULTS:
        raise ValueError(f"result must be one of {RESULTS}")
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault(pick_id, {})[tier] = result
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    return data


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    try:
        set_result(*sys.argv[1:])
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    print(f"Recorded: {sys.argv[1]} {sys.argv[2]} multi = {sys.argv[3].lower()}")
