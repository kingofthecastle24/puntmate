"""
challenge_tracker.py — the public "$100 to $1,000 Challenge" ledger.

Phase 2 of the growth plan (see PUNTMATE_GROWTH_PLAN.md in Micah's folder):
a publicly tracked challenge balance that follows PuntMate's own posted
picks — the same picks everyone sees, posted before kickoff, so the record
is provably not cherry-picked. The weekly recap shows the balance moving.

DISABLED BY DEFAULT. Start it by editing config/challenge.json:
    {"enabled": true, "start_balance": 100.0, "goal": 1000.0}
The first run after enabling stamps "started" with that day's date and only
picks from that date onward ever count. Flip enabled back to false to pause
(history is kept).

Rules (deliberately simple and deterministic):
  - Follows settled DAILY picks only (from data/picks.json, resolved by
    check_results.py). Multis are excluded: weekend multi legs aren't
    tracked as individual rows in picks.json, and mixing bet types would
    make the record harder to audit publicly.
  - Each pick gets 10% of the current balance (rounded to the cent).
  - Win: balance += stake * (odds - 1). Loss: balance -= stake.
    Push/manual/void: no change, recorded as a skip.
  - Goal reached: challenge marked complete, no further picks applied.
  - Balance below $1: marked "busted" — that's a real possible outcome and
    it stays on the record; restart by resetting config + deleting the
    ledger. Honesty is the product.
  - Each pick id is applied at most once (idempotent across re-runs).

Public copy rules: never call it a bankroll, never suggest anyone stake
anything — those phrases are banned by copy_validator and the ban applies
here too. The public line is just the challenge state, e.g.:
    Challenge: $100 -> $1,000 · now $142.50 (12 picks in)

Runs in check_results.yml straight after check_results.py resolves scores.
"""

import json
import os
from datetime import datetime, timezone

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "challenge.json")
LEDGER_PATH = os.path.join(REPO_ROOT, "data", "challenge.json")
PICKS_PATH = os.path.join(REPO_ROOT, "data", "picks.json")

STAKE_FRACTION = 0.10
BUST_FLOOR = 1.0


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"enabled": False}
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def load_ledger(cfg):
    if os.path.exists(LEDGER_PATH):
        with open(LEDGER_PATH) as f:
            return json.load(f)
    return {
        "balance": float(cfg.get("start_balance", 100.0)),
        "goal": float(cfg.get("goal", 1000.0)),
        "status": "running",  # running | complete | busted
        "picks_applied": 0,
        "history": [],
    }


def save_ledger(ledger):
    os.makedirs(os.path.dirname(LEDGER_PATH), exist_ok=True)
    with open(LEDGER_PATH, "w") as f:
        json.dump(ledger, f, indent=2)
        f.write("\n")


def _applied_ids(ledger):
    return {h["pick_id"] for h in ledger["history"]}


def apply_settled_picks(cfg=None, picks=None):
    """Apply any newly settled daily picks to the challenge balance.
    Returns the ledger (or None when the challenge is disabled)."""
    cfg = cfg if cfg is not None else load_config()
    if not cfg.get("enabled"):
        return None

    if not cfg.get("started"):
        cfg["started"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        save_config(cfg)
        print(f"Challenge started {cfg['started']} — only picks from this date onward count.")

    ledger = load_ledger(cfg)
    if ledger["status"] != "running":
        print(f"Challenge is {ledger['status']} — no new picks applied.")
        return ledger

    if picks is None:
        with open(PICKS_PATH) as f:
            picks = json.load(f)

    applied = _applied_ids(ledger)
    settled = [
        p for p in picks
        if p.get("date", "") >= cfg["started"]
        and p.get("result") in ("win", "loss", "push")
        and p.get("id") not in applied
    ]
    settled.sort(key=lambda p: (p.get("date", ""), p.get("id", "")))

    for p in settled:
        if ledger["status"] != "running":
            break
        stake = round(ledger["balance"] * STAKE_FRACTION, 2)
        result = p["result"]
        if result == "win":
            pnl = round(stake * (float(p["odds"]) - 1.0), 2)
        elif result == "loss":
            pnl = -stake
        else:  # push
            pnl = 0.0
        ledger["balance"] = round(ledger["balance"] + pnl, 2)
        ledger["picks_applied"] += 1
        ledger["history"].append({
            "pick_id": p["id"],
            "date": p["date"],
            "match": p.get("match", ""),
            "pick": p.get("pick", ""),
            "odds": p.get("odds"),
            "result": result,
            "challenge_stake": stake,
            "pnl": pnl,
            "balance_after": ledger["balance"],
        })
        print(f"  {p['date']} {p.get('match','')[:40]} {result.upper():5} {pnl:+.2f} -> ${ledger['balance']:.2f}")

        if ledger["balance"] >= ledger["goal"]:
            ledger["status"] = "complete"
            print(f"CHALLENGE COMPLETE — ${ledger['balance']:.2f} (goal ${ledger['goal']:.0f})")
        elif ledger["balance"] < BUST_FLOOR:
            ledger["status"] = "busted"
            print(f"Challenge busted at ${ledger['balance']:.2f} — it stays on the record.")

    save_ledger(ledger)
    if not settled:
        print("Challenge: no newly settled picks to apply.")
    return ledger


def public_line(ledger=None, cfg=None):
    """One public-copy-safe line for the weekly recap. Empty string when the
    challenge is disabled or hasn't applied a pick yet."""
    cfg = cfg if cfg is not None else load_config()
    if not cfg.get("enabled"):
        return ""
    if ledger is None:
        if not os.path.exists(LEDGER_PATH):
            return ""
        with open(LEDGER_PATH) as f:
            ledger = json.load(f)
    if ledger["picks_applied"] == 0:
        return ""
    start = float(cfg.get("start_balance", 100.0))
    n = ledger["picks_applied"]
    if ledger["status"] == "complete":
        return (f"🏆 The ${start:.0f} → ${ledger['goal']:.0f} Challenge: DONE — "
                f"finished at ${ledger['balance']:.2f} after {n} picks, all posted before kickoff.")
    if ledger["status"] == "busted":
        return (f"💥 The ${start:.0f} → ${ledger['goal']:.0f} Challenge busted at "
                f"${ledger['balance']:.2f} after {n} picks. It stays on the record — that's the deal.")
    return (f"🏆 The ${start:.0f} → ${ledger['goal']:.0f} Challenge: ${ledger['balance']:.2f} "
            f"after {n} picks — every one posted before kickoff.")


if __name__ == "__main__":
    ledger = apply_settled_picks()
    if ledger is None:
        print("Challenge disabled (config/challenge.json) — nothing to do.")
    else:
        line = public_line(ledger)
        if line:
            print(line)
