#!/usr/bin/env python3
"""
schedule_guard.py — Item 5 DST-regime guard (2026-10-14, Micah decided:
picks land at 7:00am NZ time).

generate.yml fires two companion cron entries for each logical trigger
(daily / weekend-extra / weekend-multi): one built for NZDT (UTC+13), one
for NZST (UTC+12), exactly one hour apart in UTC — a GitHub Actions cron
can't express a time zone, so no single fixed UTC time is correct
year-round. On any given day only ONE of the two actually lands in the
intended NZ-local 6:50am buffer; the other is an hour off for today's
real DST regime and must be a clean no-op, not a duplicate run.

Prints "true" or "false" to stdout for the calling workflow step to
capture as a job output. True means: it is currently NZ-local hour 6 (the
6:50am-local buffer ahead of the 7:00am NZ send time) — this is today's
correct firing. False means this is the companion cron's turn to no-op.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from nz_date import is_todays_dst_regime_fire

TARGET_HOUR = 6  # matches the :50 buffer crons in generate.yml (6:50am-local)

if __name__ == "__main__":
    print("true" if is_todays_dst_regime_fire(TARGET_HOUR) else "false")
