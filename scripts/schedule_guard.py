#!/usr/bin/env python3
"""Select the DST companion cron without rejecting delayed GitHub runs.

The workflow passes github.event.schedule through SCHEDULED_CRON. stdout
is exactly "true" or "false" for its proceed output. In NZDT the 17 UTC
companion is accepted; in NZST the 18 UTC companion is accepted. Runner
lateness does not change that selection. Manual dispatch bypasses the
output in generate.yml, so an absent schedule may safely return false.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from nz_date import is_todays_dst_regime_fire

TARGET_HOUR = 6  # 6:50am NZ-local buffer before the 7:00am target

if __name__ == "__main__":
    scheduled_cron = os.environ.get("SCHEDULED_CRON", "")
    print("true" if is_todays_dst_regime_fire(TARGET_HOUR, scheduled_cron) else "false")
