#!/usr/bin/env python3
"""
generate_results_post.py — Generate a Telegram-ready results post from the picks ledger.

Usage:
    python scripts/generate_results_post.py
    python scripts/generate_results_post.py --round R19
"""

import json
import sys
from pathlib import Path

LEDGER_PATH = Path(__file__).parent.parent / "data" / "results" / "picks_ledger.json"

TYPE_CONFIG = {
    "INVESTOR": {"emoji": "🏦", "label": "INVESTOR RECORD"},
    "PUNTER":   {"emoji": "🎯", "label": "PUNTER RECORD"},
    "GAMBLER":  {"emoji": "🎰", "label": "GAMBLER RECORD"},
}


def load_ledger() -> dict:
    with open(LEDGER_PATH) as f:
        return json.load(f)


def summarise_picks(picks: list[dict]) -> dict:
    """Return per-type and overall stats, excluding PENDING picks."""
    stats = {t: {"wins": 0, "losses": 0, "profit": 0.0} for t in TYPE_CONFIG}

    for pick in picks:
        if pick["result"] == "PENDING":
            continue
        t = pick["type"]
        if t not in stats:
            continue
        if pick["result"] == "WIN":
            stats[t]["wins"] += 1
        elif pick["result"] == "LOSS":
            stats[t]["losses"] += 1
        if pick["profit_loss"] is not None:
            stats[t]["profit"] += pick["profit_loss"]

    return stats


def format_profit(amount: float) -> str:
    if amount >= 0:
        return f"+${amount:.2f}"
    return f"-${abs(amount):.2f}"


def get_round_label(picks: list[dict]) -> str:
    rounds = sorted({p["round"] for p in picks if p["result"] != "PENDING"})
    return " · ".join(rounds) if rounds else "All rounds"


def generate_post(picks: list[dict]) -> str:
    stats = summarise_picks(picks)

    lines = ["📊 *PUNTMATE RESULTS UPDATE*", ""]

    for type_key, cfg in TYPE_CONFIG.items():
        s = stats[type_key]
        total = s["wins"] + s["losses"]
        if total == 0:
            continue
        pl_str = format_profit(s["profit"])
        lines.append(f"{cfg['emoji']} *{cfg['label']}*")
        lines.append(f"W: {s['wins']} | L: {s['losses']} | Profit: {pl_str} (on $10 units)")
        lines.append("")

    # Overall
    total_wins = sum(s["wins"] for s in stats.values())
    total_losses = sum(s["losses"] for s in stats.values())
    total_profit = sum(s["profit"] for s in stats.values())
    pl_str = format_profit(total_profit)

    lines.append(f"*OVERALL: {pl_str} | {total_wins}W {total_losses}L*")

    round_label = get_round_label(picks)
    lines.append(f"_{round_label} · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz_")

    return "\n".join(lines)


def main():
    round_filter = None
    if "--round" in sys.argv:
        idx = sys.argv.index("--round")
        if idx + 1 < len(sys.argv):
            round_filter = sys.argv[idx + 1].upper()

    ledger = load_ledger()
    picks = ledger["picks"]

    if round_filter:
        picks = [p for p in picks if p["round"].upper() == round_filter]
        if not picks:
            print(f"No picks found for round '{round_filter}'.")
            sys.exit(1)

    settled = [p for p in picks if p["result"] != "PENDING"]
    pending = [p for p in picks if p["result"] == "PENDING"]

    if not settled:
        print("No settled picks to report yet.")
        if pending:
            print(f"\nPending ({len(pending)}):")
            for p in pending:
                print(f"  [{p['id']}] {p['match']} — {p['selection']} @ {p['approx_odds']}")
        sys.exit(0)

    post = generate_post(picks)
    print(post)

    if pending:
        print(f"\n⏳ *PENDING ({len(pending)})*")
        for p in pending:
            print(f"  [{p['id']}] {p['match']} — {p['selection']} @ {p['approx_odds']}")


if __name__ == "__main__":
    main()
