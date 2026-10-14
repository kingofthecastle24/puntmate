#!/usr/bin/env python3
"""
hold_until_send_time.py — publish-time hold (Item 5, 2026-10-14, Micah
decided: picks should land at 7:00am NZ time).

Scheduled generate/publish runs fire a few minutes early (the 6:50am
NZ-local buffer crons in generate.yml) so there's room for odds/research/
Claude/render before this runs. This step is what actually paces the
PUBLIC POST to land at 7:00:00 Pacific/Auckland, not whenever the
pipeline happens to finish that morning.

The calling workflow step is gated to skip this entirely for manual
workflow_dispatch runs (see generate.yml) -- a human testing the
pipeline shouldn't be made to wait for a wall-clock target that doesn't
apply to them, so this script assumes it's only ever invoked for a real
scheduled run.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from nz_date import seconds_until_nz_time, nz_now_iso

if __name__ == "__main__":
    wait = seconds_until_nz_time(hour=7, minute=0)
    if wait <= 0:
        print(f"Already at/past 7:00am NZT (now: {nz_now_iso()}) — publishing now.")
    else:
        print(f"Holding {wait:.0f}s until 7:00am NZT (now: {nz_now_iso()})...")
        time.sleep(wait)
        print(f"7:00am NZT reached (now: {nz_now_iso()}) — publishing now.")
