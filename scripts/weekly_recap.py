#!/usr/bin/env python3
"""
weekly_recap.py — Phase 6. Weekly results recap broken down by bet type.

Reads data/picks.json (the live ledger check_results.py resolves daily),
takes the trailing 7 days, and produces:
  - a Telegram post: overall strike rate + W-L per bet type (Investor /
    Punter / Gambler), pending count, and No-Bet/Watchlist day count
  - an appended section in RECAP.md (permanent history)

Honesty rules, non-negotiable:
  - only picks whose "result" is win/loss count toward strike rate; pending
    and unresolved picks are shown as pending, never guessed
  - No-Bet days are reported, not hidden — they're part of the record
  - if there were zero settled picks this week, the post says exactly that

Honors DRY_RUN (default true) — prints the post instead of sending.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from copy_validator import check_internal_leak, check_staking_language

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
PICKS_PATH = os.path.join(REPO_ROOT, "data", "picks.json")
STATE_DIR = os.path.join(REPO_ROOT, "data", "state")
RECAP_PATH = os.path.join(REPO_ROOT, "RECAP.md")

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")

BET_TYPE_LABELS = {
    "INVESTOR_BET": ("📊", "Investor"),
    "PUNTER_BET": ("🎯", "Punter"),
    "GAMBLER_BET": ("🎰", "Gambler"),
}
RESPONSIBLE_LINE = "⚠️ For entertainment & informational purposes only. Not advice. 18+."


def week_window(today=None):
    today = today or datetime.now(timezone.utc).date()
    start = today - timedelta(days=6)
    return start, today


RECORD_START_PATH = os.path.join(REPO_ROOT, "config", "record_start_date")


def record_start_date():
    """Fresh-record cutoff (Micah, 2026-07-19): the public record counts
    from this date onward — everything earlier (pre-rebuild three-personality
    picks + the rebuild's shakedown week) stays in data/picks.json for
    history/settlement but is excluded from every public stat. Returns None
    (no cutoff) if the config file is absent."""
    if not os.path.exists(RECORD_START_PATH):
        return None
    with open(RECORD_START_PATH) as f:
        value = f.read().strip()
    return value or None


def load_picks():
    if not os.path.exists(PICKS_PATH):
        return []
    with open(PICKS_PATH) as f:
        picks = json.load(f)
    cutoff = record_start_date()
    if cutoff:
        picks = [p for p in picks if p.get("date", "") >= cutoff]
    return picks


def _empty_bucket():
    return {"wins": 0, "losses": 0, "pushes": 0, "pending": 0, "odds": []}


def build_stats(picks, start, end):
    """Per-bet-type and overall W/L/push/pending for picks dated within
    [start, end].

    - "manual" (check_results couldn't auto-resolve) and any unknown result
      count as pending — never guessed into a W or an L.
    - "push" is a real settled outcome (a totals-market tie), not an
      unresolved one — it used to be miscounted into "pending" here, which
      made a genuinely-settled push look like it was still awaiting a
      result (2026-10-11, external audit item 5: "define voids/pushes
      separately"). It now gets its own bucket: excluded from strike rate
      (same as before — a push isn't a win or a loss) but no longer
      conflated with "still waiting."
    - Picks from before the single-pick rebuild have no bet_type; they're
      tracked in an explicit "LEGACY" bucket so overall and per-tier numbers
      always reconcile in public — nothing silently dropped, nothing
      double-counted.
    - `odds` collects the decimal odds of every settled (win/loss) pick in
      that bucket, for the average-odds metric below — pending/push picks
      don't have a realised result to average in.
    """
    stats = {bt: _empty_bucket() for bt in BET_TYPE_LABELS}
    stats["LEGACY"] = _empty_bucket()
    overall = _empty_bucket()
    for p in picks:
        try:
            d = datetime.strptime(p.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        if not (start <= d <= end):
            continue
        bt = p.get("bet_type")
        result = (p.get("result") or "pending").lower()
        bucket = stats.get(bt) if bt in BET_TYPE_LABELS else stats["LEGACY"]
        key = "wins" if result == "win" else "losses" if result == "loss" else "pushes" if result == "push" else "pending"
        bucket[key] += 1
        overall[key] += 1
        if key in ("wins", "losses"):
            try:
                odds = float(p.get("odds"))
                bucket["odds"].append(odds)
                overall["odds"].append(odds)
            except (TypeError, ValueError):
                pass
    return stats, overall


# Below this many settled (win+loss) picks, a strike rate is too noisy to
# read as a real signal — flagged rather than presented bare (2026-10-11,
# external audit item 5: "flag small samples/uncalibrated probabilities").
SMALL_SAMPLE_FLOOR = 15


def average_odds(bucket):
    odds = bucket.get("odds") or []
    return round(sum(odds) / len(odds), 2) if odds else None


def _internal_metrics_report(stats, overall, picks, start, end):
    """ROI (net profit / total staked) on a FLAT 1-unit-per-pick basis —
    "if every settled pick this week had been backed for the same
    amount" — not any real stake of Micah's; this pipeline doesn't track
    or assume one (see this task's own instructions: "never assume a
    stake/bankroll"). Deliberately INTERNAL ONLY, never part of the
    public Telegram text: copy_validator's STAKE_PHRASES bans stake-sizing
    language from public copy project-wide, and publishing an ROI number
    at all implies a stake size, flat or not. Printed to the run log/job
    summary only, for Micah's own read on performance (2026-10-11,
    external audit item 5: "ROI (net profit/total stake)")."""
    def _in_window(p):
        try:
            d = datetime.strptime(p.get("date", ""), "%Y-%m-%d").date()
        except ValueError:
            return False
        return start <= d <= end

    settled_picks = [
        p for p in picks
        if _in_window(p) and (p.get("result") or "").lower() in ("win", "loss")
    ]

    def roi_for(bet_types):
        relevant = [p for p in settled_picks if p.get("bet_type") in bet_types] if bet_types else settled_picks
        if not relevant:
            return None
        net = 0.0
        for p in relevant:
            try:
                odds = float(p["odds"])
            except (KeyError, TypeError, ValueError):
                continue
            net += (odds - 1) if p["result"].lower() == "win" else -1
        return round(net / len(relevant) * 100, 1)

    lines = [f"[internal only, flat 1-unit basis, not public] {start} to {end}:"]
    overall_roi = roi_for(None)
    lines.append(f"  Overall ROI: {overall_roi:+.1f}% (n={len(settled_picks)})" if overall_roi is not None else "  Overall ROI: n/a (nothing settled)")
    for bt, (_, label) in BET_TYPE_LABELS.items():
        roi = roi_for({bt})
        n = stats[bt]["wins"] + stats[bt]["losses"]
        if n:
            lines.append(f"  {label} ROI: {roi:+.1f}% (n={n})")
    return "\n".join(lines)


def count_no_bet_days(start, end):
    """No-Bet/Watchlist days recorded this week (from data/state pick_ids)."""
    days = set()
    if not os.path.isdir(STATE_DIR):
        return 0
    for name in os.listdir(STATE_DIR):
        if "_no-bet" not in name:
            continue
        try:
            d = datetime.strptime(name[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if start <= d <= end:
            days.add(d)
    return len(days)


def strike_rate(wins, losses):
    total = wins + losses
    return f"{wins / total * 100:.0f}%" if total else "—"


def build_recap_text(stats, overall, no_bet_days, start, end):
    lines = [
        "*📈 PUNTMATE NZ — WEEKLY RECAP*",
        f"_{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}_",
        "",
    ]
    settled = overall["wins"] + overall["losses"]
    total_picks = settled + overall["pushes"] + overall["pending"]
    if total_picks == 0:
        lines.append("Quiet week — no picks put up. No-bet days protect the record.")
    else:
        rate_line = f"*Overall: {overall['wins']}W – {overall['losses']}L  ·  Strike rate {strike_rate(overall['wins'], overall['losses'])}*"
        avg = average_odds(overall)
        if avg is not None:
            rate_line += f"  ·  Avg odds {avg:.2f}"
        lines.append(rate_line)
        if 0 < settled < SMALL_SAMPLE_FLOOR:
            lines.append(f"_Small sample ({settled} settled) — read the strike rate with caution._")
        lines.append("")
        for bt, (emoji, label) in BET_TYPE_LABELS.items():
            s = stats[bt]
            if s["wins"] + s["losses"] + s["pushes"] + s["pending"] == 0:
                continue
            line = f"{emoji} {label}: {s['wins']}W – {s['losses']}L  ({strike_rate(s['wins'], s['losses'])})"
            avg_bt = average_odds(s)
            if avg_bt is not None:
                line += f"  · avg {avg_bt:.2f}"
            lines.append(line)
        legacy = stats.get("LEGACY", _empty_bucket())
        if legacy["wins"] + legacy["losses"] > 0:
            lines.append(f"📁 Pre-rebuild picks: {legacy['wins']}W – {legacy['losses']}L (counted in overall)")
        if overall["pushes"]:
            lines.append("")
            lines.append(f"🔁 {overall['pushes']} push(es) this week — no win or loss, excluded from strike rate.")
        if overall["pending"]:
            lines.append("")
            lines.append(f"⏳ {overall['pending']} pick(s) still to settle — counted next week, never guessed.")
    if no_bet_days:
        lines.append("")
        lines.append(f"🔍 {no_bet_days} no-bet day(s) this week — nothing cleared the bar, so nothing was forced.")
    # Phase 2 growth: the $100 -> $1,000 challenge line, only when the
    # challenge is enabled and has actually applied at least one pick.
    # public_line() is written to satisfy copy_validator (no staking
    # language, no "bankroll") and the whole recap still passes through
    # check_internal_leak below like always.
    try:
        from challenge_tracker import public_line
        challenge_line = public_line()
    except Exception as e:
        print(f"::warning::challenge line skipped: {e}")
        challenge_line = ""
    if challenge_line:
        lines += ["", challenge_line]

    lines += [
        "",
        "Every result on the record, wins and losses alike.",
        "",
        "──────────────────",
        "📲 Join Telegram for daily picks",
        RESPONSIBLE_LINE,
    ]
    return "\n".join(lines)


def append_recap_md(text, start, end):
    header = f"\n\n## Week {start.isoformat()} → {end.isoformat()} (auto-generated)\n\n"
    body = "```\n" + text + "\n```\n"
    with open(RECAP_PATH, "a") as f:
        f.write(header + body)


def main():
    start, end = week_window()
    picks = load_picks()
    stats, overall = build_stats(picks, start, end)
    no_bet_days = count_no_bet_days(start, end)
    text = build_recap_text(stats, overall, no_bet_days, start, end)

    # Internal only -- see _internal_metrics_report's docstring for why
    # this is printed (job summary / log), never posted publicly.
    print(_internal_metrics_report(stats, overall, picks, start, end))

    # Same gates as every other public post — a recap is public copy too.
    # check_staking_language added 2026-10-11 (external audit item 5):
    # the new avg-odds/ROI-adjacent metrics below are an easy place to
    # accidentally reintroduce "units"/"bankroll"/stake-size language, so
    # this file now checks for that itself rather than relying on
    # self-discipline alone.
    violations = check_internal_leak(text) + check_staking_language(text)
    if violations:
        print("::error::weekly recap failed public-copy validation — refusing to post:")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)

    if DRY_RUN:
        print("DRY RUN — weekly recap that WOULD be posted:")
        print("-" * 55)
        print(text)
        print("-" * 55)
        return

    from post_telegram import post_text
    r = post_text(text)
    ok = bool(r and r.get("ok", True))
    print(f"Telegram recap post: {'OK' if ok else 'FAILED'} — {r}")
    append_recap_md(text, start, end)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
