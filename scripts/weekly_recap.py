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
from copy_validator import check_internal_leak

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
RESPONSIBLE_LINE = "Problem Gambling Foundation NZ: 0800 664 262"


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


def build_stats(picks, start, end):
    """Per-bet-type and overall W/L/pending for picks dated within [start, end].

    - "manual" (check_results couldn't auto-resolve) and any unknown result
      counts as pending — never guessed into a W or an L.
    - Picks from before the single-pick rebuild have no bet_type; they're
      tracked in an explicit "LEGACY" bucket so overall and per-tier numbers
      always reconcile in public — nothing silently dropped, nothing
      double-counted.
    """
    stats = {bt: {"wins": 0, "losses": 0, "pending": 0} for bt in BET_TYPE_LABELS}
    stats["LEGACY"] = {"wins": 0, "losses": 0, "pending": 0}
    overall = {"wins": 0, "losses": 0, "pending": 0}
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
        key = "wins" if result == "win" else "losses" if result == "loss" else "pending"
        bucket[key] += 1
        overall[key] += 1
    return stats, overall


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
    if settled == 0 and overall["pending"] == 0:
        lines.append("Quiet week — no picks put up. No-bet days protect the record.")
    else:
        lines.append(f"*Overall: {overall['wins']}W – {overall['losses']}L  ·  Strike rate {strike_rate(overall['wins'], overall['losses'])}*")
        lines.append("")
        for bt, (emoji, label) in BET_TYPE_LABELS.items():
            s = stats[bt]
            if s["wins"] + s["losses"] + s["pending"] == 0:
                continue
            lines.append(f"{emoji} {label}: {s['wins']}W – {s['losses']}L  ({strike_rate(s['wins'], s['losses'])})")
        legacy = stats.get("LEGACY", {"wins": 0, "losses": 0, "pending": 0})
        if legacy["wins"] + legacy["losses"] > 0:
            lines.append(f"📁 Pre-rebuild picks: {legacy['wins']}W – {legacy['losses']}L (counted in overall)")
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
        f"R18 · Gamble responsibly · {RESPONSIBLE_LINE}",
    ]
    return "\n".join(lines)


def append_recap_md(text, start, end):
    header = f"\n\n## Week {start.isoformat()} → {end.isoformat()} (auto-generated)\n\n"
    body = "```\n" + text + "\n```\n"
    with open(RECAP_PATH, "a") as f:
        f.write(header + body)


def main():
    start, end = week_window()
    stats, overall = build_stats(load_picks(), start, end)
    no_bet_days = count_no_bet_days(start, end)
    text = build_recap_text(stats, overall, no_bet_days, start, end)

    # Same leak gate as every other public post — a recap is public copy too.
    leaks = check_internal_leak(text)
    if leaks:
        print("::error::weekly recap failed internal-leak validation — refusing to post:")
        for v in leaks:
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
