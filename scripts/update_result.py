#!/usr/bin/env python3
"""
update_result.py — Mark a pick as WIN, LOSS, or VOID in the picks ledger.

Usage:
    python scripts/update_result.py <pick_id> <result>

Examples:
    python scripts/update_result.py R19-001 WIN
    python scripts/update_result.py R19-001 LOSS
    python scripts/update_result.py R19-001 VOID
"""

import json
import sys
from pathlib import Path

LEDGER_PATH = Path(__file__).parent.parent / "data" / "results" / "picks_ledger.json"
VALID_RESULTS = {"WIN", "LOSS", "VOID", "PENDING"}


def calculate_profit_loss(result: str, odds: float, stake: float) -> float | None:
    if result == "WIN":
        return round((odds - 1) * stake, 2)
    elif result == "LOSS":
        return -stake
    elif result == "VOID":
        return 0.0
    return None  # PENDING


def load_ledger() -> dict:
    with open(LEDGER_PATH) as f:
        return json.load(f)


def save_ledger(ledger: dict) -> None:
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2)


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/update_result.py <pick_id> <result>")
        print(f"Valid results: {', '.join(VALID_RESULTS)}")
        sys.exit(1)

    pick_id = sys.argv[1].upper()
    result = sys.argv[2].upper()

    if result not in VALID_RESULTS:
        print(f"Error: Invalid result '{result}'. Must be one of: {', '.join(VALID_RESULTS)}")
        sys.exit(1)

    ledger = load_ledger()

    pick = next((p for p in ledger["picks"] if p["id"] == pick_id), None)
    if pick is None:
        print(f"Error: Pick '{pick_id}' not found in ledger.")
        sys.exit(1)

    pick["result"] = result
    pick["profit_loss"] = calculate_profit_loss(result, pick["approx_odds"], pick["stake"])

    save_ledger(ledger)

    pl = pick["profit_loss"]
    pl_str = f"+${pl:.2f}" if pl and pl > 0 else (f"-${abs(pl):.2f}" if pl and pl < 0 else "$0.00")
    print(f"Updated: [{pick_id}] {pick['match']} — {pick['selection']}")
    print(f"  Result: {result} | P/L: {pl_str}")


if __name__ == "__main__":
    main()
