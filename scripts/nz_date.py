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
