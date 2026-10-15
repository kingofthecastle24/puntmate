"""
quota_budget.py — hard, durable credit budget for The Odds API (2026-10-15
redesign: "research first, price second"). Run #206 (14 Oct) burned the
account to 0/500 remaining credits on the free plan by scanning all 14
registered sports on every single run; every call now 401s until the
provider resets usage on 1 Nov 2026. This module is what stops that from
ever happening again: every paid call MUST reserve budget here first, and
a reservation is refused (fails closed) whenever the effective remaining
allowance is unknown or exhausted — never "try it and see".

Design:
  - One budget record per UTC reset period, keyed by period_start_utc (ISO),
    persisted in data/quota_budget.json. Never auto-rolled: a new period is
    only opened by an explicit, provider-confirmed reset (see
    start_new_period). Letting the clock alone roll the period would spend
    against a balance nobody has verified.
  - Two buckets: "odds" (the per-sport odds scan) and "scores" (the
    settlement /scores calls). Each has its own monthly credit limit.
  - reserve() is atomic-enough for this pipeline's actual concurrency model:
    generate.yml and check_results.yml never run the same bucket
    concurrently in practice (see their own concurrency groups), and this
    module always re-reads the file immediately before writing it, so the
    window for a real double-spend is a same-process double-call, not a
    cross-job race. It is not a general-purpose distributed lock.
  - A reservation is NEVER silently dropped on a request timeout — the
    provider may have charged it even though the client never saw the
    response. Only confirm() (success) or release() (the call never went
    out at all, e.g. zero candidates) remove a reservation from the
    outstanding total; mark_uncertain() keeps it charged against the budget
    forever (for this period) rather than guessing it didn't land.
  - Effective allowance is min(local bucket balance, provider-reported
    remaining). Until the provider's remaining count has been synced at
    least once this period (via reconcile_provider_headers, fed from any
    real response's x-requests-remaining header, including the quota-free
    /sports catalog check), the provider side of that min() is treated as
    0 — fails closed, never optimistic.
"""
import json
import os
import uuid
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
BUDGET_PATH = os.path.join(REPO_ROOT, "data", "quota_budget.json")

ODDS = "odds"
SCORES = "scores"
BUCKETS = (ODDS, SCORES)

RESERVED = "reserved"
CONFIRMED = "confirmed"
RELEASED = "released"
UNCERTAIN = "uncertain"

# Monthly hard caps from the budget design (Section 5): 56 worst-case scans
# x 2 sports x 3 markets x 1 region = 336 odds credits; 2 sport-score calls/
# day x 2 credits x 31 days = 124 scores credits. 40 credits held back,
# unallocated, as a safety reserve never auto-spent by this module.
DEFAULT_LIMITS = {ODDS: 336, SCORES: 124}
UNALLOCATED_RESERVE = 40


# The ONE period this redesign inherits a confirmed, concrete fact about
# (Section 2): the free-tier account sat at 0/500 remaining as of 14-15
# Oct 2026, and the provider's own next reset is Sunday 1 Nov 2026, 1pm
# NZDT = 00:00 UTC. The account's actual monthly cycle start isn't known
# (free-tier resets aren't necessarily calendar-month-aligned), so this
# period is keyed by an opaque label rather than a guessed start time.
# Opening the NEXT period after this one requires a provider-confirmed
# remaining count via start_new_period() — never assumed from the clock
# alone (see that function's docstring) — so no constant is defined here
# for whatever comes after 1 Nov; that reconciliation happens when it
# happens, against real data, not a hardcoded guess made today.
CURRENT_PERIOD_KEY = "2026-10-exhausted"
CURRENT_PERIOD_RESET_UTC = "2026-11-01T00:00:00+00:00"


def ensure_current_period():
    """Idempotently seed CURRENT_PERIOD_KEY as exhausted if it doesn't
    exist yet. Safe to call at the top of every pipeline run — a no-op
    once the period record already exists."""
    return init_exhausted_period(CURRENT_PERIOD_KEY, CURRENT_PERIOD_RESET_UTC)


def _now_iso(now_utc=None):
    return (now_utc or datetime.now(timezone.utc)).isoformat()


def _empty_period(period_start_utc, period_reset_utc, limits=None):
    limits = dict(limits or DEFAULT_LIMITS)
    return {
        "period_start_utc": period_start_utc,
        "period_reset_utc": period_reset_utc,
        "provider_remaining": None,
        "provider_used": None,
        "provider_last_sync_utc": None,
        "buckets": {b: {"limit": limits.get(b, 0), "charged": 0, "reserved_total": 0} for b in BUCKETS},
        "unallocated_reserve": UNALLOCATED_RESERVE,
        "reservations": {},
    }


def _load_all():
    if not os.path.exists(BUDGET_PATH):
        return {"schema_version": 1, "periods": {}}
    with open(BUDGET_PATH) as f:
        return json.load(f)


def _save_all(data):
    os.makedirs(os.path.dirname(BUDGET_PATH), exist_ok=True)
    with open(BUDGET_PATH, "w") as f:
        json.dump(data, f, indent=2)


def get_period(period_start_utc):
    """Load the named period's record, or None if it has never been created
    (callers must go through start_new_period or init_exhausted_period
    before reserving against a period that doesn't exist yet — there is no
    implicit "create on first use" that could paper over an un-reconciled
    reset)."""
    return _load_all().get("periods", {}).get(period_start_utc)


def current_period_key(data=None):
    """The most recently opened period's key, or None if none exist yet."""
    data = data if data is not None else _load_all()
    periods = data.get("periods", {})
    if not periods:
        return None
    return max(periods.keys())


def init_exhausted_period(period_start_utc, period_reset_utc, limits=None):
    """Seed a period record that starts fully spent — used once, for the
    October 2026 period this redesign inherits: real usage before this
    module existed already consumed the account's allowance (run #206:
    0/500 remaining), so the honest starting state is "exhausted", not
    "unknown". Idempotent: a period that already exists is left untouched
    (never overwrites real reservation history)."""
    data = _load_all()
    data.setdefault("periods", {})
    if period_start_utc in data["periods"]:
        return data["periods"][period_start_utc]
    rec = _empty_period(period_start_utc, period_reset_utc, limits)
    for b in BUCKETS:
        rec["buckets"][b]["charged"] = rec["buckets"][b]["limit"]
    rec["provider_remaining"] = 0
    rec["provider_last_sync_utc"] = _now_iso()
    data["periods"][period_start_utc] = rec
    _save_all(data)
    return rec


def start_new_period(period_start_utc, period_reset_utc, confirmed_provider_remaining, limits=None, now_utc=None):
    """Open a fresh period record. Requires a provider-CONFIRMED remaining
    count (e.g. read from a quota-free /sports call right after the
    provider's own reset) — never opened on a bare clock rollover, per the
    design doc ("reconcile a provider-confirmed UTC reset before opening a
    new period"). Idempotent per period_start_utc."""
    if confirmed_provider_remaining is None:
        raise ValueError("start_new_period requires a provider-confirmed remaining count")
    data = _load_all()
    data.setdefault("periods", {})
    if period_start_utc in data["periods"]:
        return data["periods"][period_start_utc]
    rec = _empty_period(period_start_utc, period_reset_utc, limits)
    rec["provider_remaining"] = confirmed_provider_remaining
    rec["provider_last_sync_utc"] = _now_iso(now_utc)
    data["periods"][period_start_utc] = rec
    _save_all(data)
    return rec


def _local_remaining(rec, bucket):
    b = rec["buckets"][bucket]
    return b["limit"] - b["charged"] - b["reserved_total"]


def effective_remaining(period_start_utc, bucket):
    """min(local bucket balance, provider-reported remaining). Provider
    remaining counts as 0 (fails closed) until at least one successful
    reconcile_provider_headers call this period — an unknown balance is
    never treated as "probably fine"."""
    rec = get_period(period_start_utc)
    if rec is None:
        return 0
    local = _local_remaining(rec, bucket)
    provider = rec.get("provider_remaining")
    if provider is None:
        return 0
    return max(0, min(local, provider))


def reserve(period_start_utc, bucket, amount, note=""):
    """Reserve `amount` credits from `bucket` for this period. Returns a
    reservation_id on success, or None if the effective remaining
    allowance can't cover it (fails closed — the caller must make zero
    requests when this returns None, not a reduced/partial scan)."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    data = _load_all()
    rec = data.get("periods", {}).get(period_start_utc)
    if rec is None:
        return None
    if effective_remaining(period_start_utc, bucket) < amount:
        return None
    reservation_id = uuid.uuid4().hex[:16]
    rec["buckets"][bucket]["reserved_total"] += amount
    rec["reservations"][reservation_id] = {
        "bucket": bucket, "amount": amount, "status": RESERVED,
        "created_utc": _now_iso(), "note": note,
    }
    _save_all(data)
    return reservation_id


def confirm(period_start_utc, reservation_id, actual_amount=None):
    """The reserved call actually happened and the provider actually
    charged it. Moves the reservation from reserved_total into charged
    (using actual_amount if the real cost differed from the reservation,
    e.g. a cheaper-than-expected response)."""
    data = _load_all()
    rec = data["periods"][period_start_utc]
    r = rec["reservations"][reservation_id]
    if r["status"] != RESERVED:
        return
    amount = r["amount"] if actual_amount is None else actual_amount
    rec["buckets"][r["bucket"]]["reserved_total"] -= r["amount"]
    rec["buckets"][r["bucket"]]["charged"] += amount
    r["status"] = CONFIRMED
    r["actual_amount"] = amount
    r["resolved_utc"] = _now_iso()
    _save_all(data)


def release(period_start_utc, reservation_id):
    """The reserved call was never actually sent (e.g. zero shortlisted
    sports, nothing to query) — give the credits back."""
    data = _load_all()
    rec = data["periods"][period_start_utc]
    r = rec["reservations"][reservation_id]
    if r["status"] != RESERVED:
        return
    rec["buckets"][r["bucket"]]["reserved_total"] -= r["amount"]
    r["status"] = RELEASED
    r["resolved_utc"] = _now_iso()
    _save_all(data)


def mark_uncertain(period_start_utc, reservation_id):
    """The call timed out or the response was lost — the provider may have
    charged it anyway. Converts the reservation straight to a charge
    (worst case assumed) rather than releasing it on a guess; never
    silently retried from here."""
    data = _load_all()
    rec = data["periods"][period_start_utc]
    r = rec["reservations"][reservation_id]
    if r["status"] != RESERVED:
        return
    rec["buckets"][r["bucket"]]["reserved_total"] -= r["amount"]
    rec["buckets"][r["bucket"]]["charged"] += r["amount"]
    r["status"] = UNCERTAIN
    r["resolved_utc"] = _now_iso()
    _save_all(data)


def reconcile_provider_headers(period_start_utc, remaining=None, used=None, last=None, now_utc=None):
    """Feed this the-odds-api.com response headers
    (x-requests-remaining/x-requests-used/x-requests-last) after ANY call
    that returns them — including the quota-free /sports catalog check,
    which is how the provider side of effective_remaining() gets synced
    without ever spending a reservation to find out. `remaining` is parsed
    as an int when present and numeric; a non-numeric or missing value
    leaves provider_remaining at its previous (possibly still-unknown)
    state rather than being coerced to 0 here — reserve()/effective_
    remaining() are what apply the fail-closed default."""
    data = _load_all()
    rec = data["periods"].get(period_start_utc)
    if rec is None:
        return
    if remaining is not None:
        try:
            rec["provider_remaining"] = int(remaining)
        except (TypeError, ValueError):
            pass
        else:
            rec["provider_last_sync_utc"] = _now_iso(now_utc)
    if used is not None:
        rec["provider_used"] = used
    if last is not None:
        rec["provider_last"] = last
    _save_all(data)
