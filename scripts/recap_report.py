#!/usr/bin/env python3
"""
recap_report.py — Compute win % per tier (and overall) from the picks ledger.

Reads data/results/picks_ledger.json (the same ledger update_result.py and
generate_results_post.py use) and prints a recap. Re-run any time after
settling new picks with update_result.py.

Usage:
    python3 scripts/recap_report.py            # print recap to terminal
    python3 scripts/recap_report.py --markdown  # print recap as Markdown
                                                 # (paste into RECAP.md, or
                                                 # redirect: ... > RECAP.md)

Notes:
- Only picks tagged INVESTOR / PUNTER / GAMBLER count toward tier and
  overall win %. MULTI-type picks (parlays) are reported separately since
  they aren't single-selection tier picks — this matches the convention
  already used in generate_results_post.py.
- PENDING and UNRESOLVED picks are excluded from win % but shown in their
  own section so nothing silently disappears.
- Never guesses a result. A pick only counts as WIN/LOSS if its "result"
  field says so.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

LEDGER_PATH = Path(__file__).parent.parent / "data" / "results" / "picks_ledger.json"

TIER_ORDER = ["INVESTOR", "PUNTER", "GAMBLER"]
TIER_EMOJI = {"INVESTOR": "🏦", "PUNTER": "🎯", "GAMBLER": "🎰"}


def load_ledger() -> dict:
    with open(LEDGER_PATH) as f:
        return json.load(f)


def fmt_pnl(amount: float) -> str:
    if amount >= 0:
        return f"+${amount:.2f}"
    return f"-${abs(amount):.2f}"


def win_pct(wins: int, losses: int) -> str:
    total = wins + losses
    if total == 0:
        return "—"
    return f"{(wins / total) * 100:.0f}%"


def build_stats(picks: list[dict]) -> dict:
    """Per-tier + overall stats for INVESTOR/PUNTER/GAMBLER picks only."""
    stats = {t: {"wins": 0, "losses": 0, "voids": 0, "profit": 0.0} for t in TIER_ORDER}

    for p in picks:
        t = p.get("type")
        if t not in TIER_ORDER:
            continue
        result = p.get("result", "PENDING")
        if result == "WIN":
            stats[t]["wins"] += 1
            stats[t]["profit"] += p.get("profit_loss") or 0.0
        elif result == "LOSS":
            stats[t]["losses"] += 1
            stats[t]["profit"] += p.get("profit_loss") or 0.0
        elif result == "VOID":
            stats[t]["voids"] += 1
        # PENDING / UNRESOLVED excluded from win% math

    return stats


def main():
    as_markdown = "--markdown" in sys.argv

    ledger = load_ledger()
    picks = ledger["picks"]

    tier_picks = [p for p in picks if p.get("type") in TIER_ORDER]
    multi_picks = [p for p in picks if p.get("type") == "MULTI"]
    pending = [p for p in picks if p.get("result") in ("PENDING", "UNRESOLVED")]

    stats = build_stats(tier_picks)

    total_wins = sum(s["wins"] for s in stats.values())
    total_losses = sum(s["losses"] for s in stats.values())
    total_profit = sum(s["profit"] for s in stats.values())

    lines = []
    if as_markdown:
        lines.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} by scripts/recap_report.py_")
        lines.append("")
        lines.append("| Tier | W | L | Win % | P&L ($10 units) |")
        lines.append("|------|---|---|-------|------------------|")
        for t in TIER_ORDER:
            s = stats[t]
            total = s["wins"] + s["losses"]
            if total == 0 and s["voids"] == 0:
                lines.append(f"| {t.title()} | 0 | 0 | — | no settled picks yet |")
                continue
            lines.append(f"| {t.title()} | {s['wins']} | {s['losses']} | {win_pct(s['wins'], s['losses'])} | {fmt_pnl(s['profit'])} |")
        lines.append(f"| **Overall** | **{total_wins}** | **{total_losses}** | **{win_pct(total_wins, total_losses)}** | **{fmt_pnl(total_profit)}** |")
    else:
        lines.append("PUNTMATE NZ — RECAP")
        lines.append("=" * 40)
        for t in TIER_ORDER:
            s = stats[t]
            total = s["wins"] + s["losses"]
            emoji = TIER_EMOJI[t]
            if total == 0 and s["voids"] == 0:
                lines.append(f"{emoji} {t.title():<10} no settled picks yet")
                continue
            lines.append(
                f"{emoji} {t.title():<10} {s['wins']}W {s['losses']}L | "
                f"Win%: {win_pct(s['wins'], s['losses']):<5} | P&L: {fmt_pnl(s['profit'])}"
            )
        lines.append("-" * 40)
        lines.append(
            f"OVERALL     {total_wins}W {total_losses}L | "
            f"Win%: {win_pct(total_wins, total_losses)} | P&L: {fmt_pnl(total_profit)}"
        )

    if multi_picks:
        settled_multis = [p for p in multi_picks if p.get("result") in ("WIN", "LOSS")]
        m_wins = sum(1 for p in settled_multis if p["result"] == "WIN")
        m_losses = sum(1 for p in settled_multis if p["result"] == "LOSS")
        m_profit = sum(p.get("profit_loss") or 0.0 for p in settled_multis)
        lines.append("")
        if as_markdown:
            lines.append(f"**Multis (tracked separately, not in tier win %):** {m_wins}W {m_losses}L | {fmt_pnl(m_profit)}")
        else:
            lines.append(f"Multis (separate from tier win%): {m_wins}W {m_losses}L | P&L: {fmt_pnl(m_profit)}")

    if pending:
        lines.append("")
        label = "**Pending / unresolved:**" if as_markdown else "Pending / unresolved:"
        lines.append(label)
        for p in pending:
            lines.append(f"  - [{p['id']}] {p['match']} — {p['selection']} @ {p['approx_odds']} ({p.get('result')})")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
