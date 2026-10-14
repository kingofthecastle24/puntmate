"""
nz_date.py — the single source of truth for "what business date is it".

2026-10-11 (external audit item 6): main.py computed run_date as the raw
UTC calendar date (datetime.now(timezone.utc).strftime('%Y-%m-%d')).
generate.yml's cron fires at a fixed UTC time (20:00 UTC, documented as
"8am NZT") — but NZ switches between NZST (UTC+12) and NZDT (UTC+13)
twice a year, so that one fixed UTC offset is only actually 8am NZT for
half the year; the other half it's 9am NZT (right now: NZ is in daylight
saving, so 20:00 UTC is 9am NZDT, not the documented 8am). GitHub Actions
scheduled workflows cannot express a time-zone-aware cron, so the fire
time will keep drifting by an hour across each DST transition — that's a
scheduling limitation this module can't fix.

What IS fixable: everything downstream that means "today" (the live
pick_id's date component, same-day dedupe, the published-content date)
should mean "today in Auckland", not "today in UTC" — a run firing at
9am NZDT instead of 8am NZT is still unambiguously the same NZ calendar
day; the two are only ever misaligned right around UTC midnight, which is
late morning/afternoon in NZ, nowhere near this pipeline's run times.
Using the UTC date there was latent — wrong only in a multi-hour window
most days never touch — but still wrong, and worth fixing at the root
rather than re-deriving it in every caller.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NZ_TZ = ZoneInfo("Pacific/Auckland")


def nz_today(now_utc=None):
    """Today's business date (YYYY-MM-DD) in Pacific/Auckland, correct
    across the NZST/NZDT transition. `now_utc` is an optional aware
    datetime, for tests; defaults to the real current time."""
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(NZ_TZ).strftime("%Y-%m-%d")


def nz_now_iso(now_utc=None):
    """Current instant as an ISO-8601 string with the Pacific/Auckland
    offset attached — same instant as now_utc, just NZ-local for display/
    log readability; use run_ts (UTC) for anything compared across runs."""
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(NZ_TZ).isoformat()


def is_todays_dst_regime_fire(target_hour, now_utc=None):
    """2026-10-14 (Item 5, Micah decided: picks land at 7:00am NZ time).
    generate.yml fires TWO companion crons for the same logical trigger,
    one built for NZDT (UTC+13) and one for NZST (UTC+12), exactly one
    hour apart in UTC -- since a GitHub Actions cron can't express a time
    zone, there is no single fixed UTC time that is correct across both
    regimes. On any given day only ONE of the two actually lands in the
    intended NZ-local hour; the other is either an hour early or an hour
    late for today's real offset. `target_hour` is the NZ-local hour the
    CALLING cron entry was built for (e.g. 6 for a 6:50am-local buffer
    ahead of a 7:00am send time); this returns True only when that is
    also the hour it is RIGHT NOW in Auckland, so exactly one of the two
    companion runs proceeds and the other is a clean no-op -- no manual
    DST-date bookkeeping needed."""
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(NZ_TZ).hour == target_hour


def seconds_until_nz_time(hour, minute=0, now_utc=None, max_wait_seconds=1800):
    """Seconds to sleep until the next occurrence of hour:minute Pacific/
    Auckland local time, TODAY only -- returns 0.0 if that time already
    passed today (never waits ~24h for "tomorrow"), and caps at
    max_wait_seconds as a safety net against holding a job open
    indefinitely if something upstream ran unexpectedly early. Used by
    the publish-time hold (Item 5): generate/publish fire a few minutes
    before 7:00am NZT so there's buffer for odds/research/render, and this
    is what actually paces the PUBLIC POST to land at 7:00:00, not
    whenever the pipeline happens to finish."""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_nz = now_utc.astimezone(NZ_TZ)
    target_nz = now_nz.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target_nz <= now_nz:
        return 0.0
    return min((target_nz - now_nz).total_seconds(), max_wait_seconds)
