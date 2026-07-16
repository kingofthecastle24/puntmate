#!/usr/bin/env python3
"""
render_latest_pick.py — TEST-ONLY companion to inject_test_pick.py. Renders
whatever pick is currently in data/latest_run.json using the same render_card()
helper main.py uses in production, so the force_test_pick path exercises the
real Playwright renderer rather than a stub.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from main import render_card, CARDS_DIR

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
LATEST_RUN_PATH = os.path.join(REPO_ROOT, "data", "latest_run.json")


def main():
    with open(LATEST_RUN_PATH) as f:
        run_data = json.load(f)
    pick = run_data.get("pick")
    if not pick or not pick.get("has_pick"):
        print("No pick to render.")
        return
    os.makedirs(CARDS_DIR, exist_ok=True)
    result = render_card(pick)
    print(f"Rendered: {result.get('files')}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"::warning:: {w}")


if __name__ == "__main__":
    main()
