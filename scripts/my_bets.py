#!/usr/bin/env python3
"""
my_bets.py — Micah's personal flat-stake bet log and budget tracker.

Separate from the public ledger (data/picks.json, $10 flat stake) and from
the public record's copy/approval/freeze machinery entirely — this is
Micah's own record of what he actually placed, at his own flat stakes
(config/my_bets.json). Used only for his private DM (owner_dm.py) and his
own summary. Never touches TAB itself (he places every bet by hand via
Claude in Chrome) and never changes anything public-facing.

data/my_bets.json schema — one entry per bet actually placed:
  pick_id : the SAME pick_id as data/review/<pick_id>/ (never a separate id)
  type    : "single" or "multi"
  tier    : "punter" | "gambler" | "degenerate" — multi only, since one
            weekend pick_id can carry both a Punter and a Gambler multi
  date    : the pick's post_date (from the frozen metadata, not "today")
  stake   : config.single_stake or config.multi_stake at the time it was
            logged (kept even if the config default changes later)
  odds    : the single's own odds, or the multi's combined odds
  result  : "pending" | "win" | "loss" | "push" | "manual" | "unresolved"
  pnl     : null until resolved

Resolution (resolve_pending, run nightly from check_results.yml right after
check_results.py) always re-reads the frozen post-metadata.json by pick_id
rather than storing a second copy of match/selection/legs here — "read it
from the same published data, never regenerate it" applies at resolution
time too. Singles and multi legs are both resolved automatically against
real scores via the same market rules check_results.py uses for the public
ledger (resolve_market_result) — nothing here is settled by hand, and a
multi's result is tracked ONLY in this file, never written into the public
data/picks.json ledger.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from check_results import fetch_scores, resolve_market_result, FLAT_STAKE as PUBLIC_FLAT_STAKE
from build_review_package import _combined_odds

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "my_bets.json")
LOG_PATH = os.path.join(REPO_ROOT, "data", "my_bets.json")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")
PICKS_PATH = os.path.join(REPO_ROOT, "data", "picks.json")

DEFAULT_CONFIG = {"single_stake": 2.00, "multi_stake": 5.00, "monthly_budget": 100.00, "tab_balance": None}
VALID_TIERS = ("punter", "gambler", "degenerate")


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def load_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH) as f:
        return json.load(f)


def save_log(entries):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def _read_metadata(pick_id):
    path = os.path.join(REVIEW_ROOT, pick_id, "post-metadata.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No frozen post-metadata.json for pick_id={pick_id!r} — can't log a bet against it."
        )
    with open(path) as f:
        return json.load(f)


def add_bet(pick_id, tier=None):
    """Append one entry for a bet Micah says he actually placed. Returns the
    new entry. Raises FileNotFoundError/ValueError on a bad pick_id/tier
    combination or a duplicate (same pick_id+tier already logged — re-run
    safe, same dedup convention as log_picks.py)."""
    metadata = _read_metadata(pick_id)
    config = load_config()
    entries = load_log()

    if tier is None:
        if not metadata.get("has_pick"):
            raise ValueError(
                f"{pick_id} has no single pick (has_pick is false) — pass --tier if this is a multi."
            )
        bet_type = "single"
        stake = float(config["single_stake"])
        odds = float(metadata["odds"])
    else:
        tier = tier.lower()
        if tier not in VALID_TIERS:
            raise ValueError(f"Unknown tier {tier!r} — must be one of {VALID_TIERS}.")
        if not metadata.get(f"has_{tier}_multi"):
            raise ValueError(f"{pick_id} has no has_{tier}_multi — nothing to log for that tier.")
        legs = metadata.get(f"{tier}_multi_legs") or []
        if not legs:
            raise ValueError(f"{pick_id}'s {tier} multi has no frozen legs to compute combined odds from.")
        bet_type = "multi"
        stake = float(config["multi_stake"])
        odds = round(_combined_odds(legs), 2)

    dup_key = (pick_id, tier)
    for e in entries:
        if (e["pick_id"], e.get("tier")) == dup_key:
            raise ValueError(f"Already logged {pick_id!r} (tier={tier!r}) — not adding a duplicate.")

    entry = {
        "pick_id": pick_id,
        "type": bet_type,
        "date": metadata.get("post_date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
        "stake": stake,
        "odds": odds,
        "result": "pending",
        "pnl": None,
    }
    if tier is not None:
        entry["tier"] = tier

    entries.append(entry)
    save_log(entries)
    print(f"Logged: {pick_id} ({bet_type}{' / ' + tier if tier else ''}) @ {odds} for ${stake:.2f}")
    return entry


def _split_match(match_str):
    home, sep, away = (match_str or "").partition(" vs ")
    return (home.strip(), away.strip()) if sep else (match_str, "")


def _score_map_for(sport_key, cache):
    """Same (home_team, away_team) -> scores lookup check_results.py builds
    inline, cached per sport_key for the duration of one resolve_pending()
    run so a weekend multi's several legs in the same sport cost one API
    call, not one per leg."""
    if sport_key not in cache:
        games = fetch_scores(sport_key)
        m = {}
        for game in games:
            if not game.get("completed"):
                continue
            key = (game["home_team"], game["away_team"])
            by_team = {s["name"]: s["score"] for s in (game.get("scores") or [])}
            m[key] = {
                "home_score": by_team.get(game["home_team"]),
                "away_score": by_team.get(game["away_team"]),
            }
        cache[sport_key] = m
    return cache[sport_key]


def _resolve_single(entry, scores_cache):
    metadata = _read_metadata(entry["pick_id"])
    home, away = _split_match(metadata.get("match", ""))
    sport_key = metadata.get("sport", "")
    score = _score_map_for(sport_key, scores_cache).get((home, away))
    if score is None:
        return None  # still pending — no completed score yet
    return resolve_market_result(
        metadata.get("market", ""), metadata.get("selection", ""),
        home, away, score["home_score"], score["away_score"],
    )


def _resolve_multi(entry, scores_cache):
    """Multis need every leg to win. A push leg is stake-neutral (same as a
    real-world void leg) — it just can't itself be the reason the multi
    wins. Any leg still pending, or "manual" (a handicap leg — see
    resolve_market_result), blocks a definite WIN verdict unless something
    else has already lost outright."""
    metadata = _read_metadata(entry["pick_id"])
    tier = entry.get("tier")
    legs = metadata.get(f"{tier}_multi_legs") or []
    if not legs:
        return None

    leg_results = []
    for leg in legs:
        home, away = _split_match(leg.get("match", ""))
        sport_key = leg.get("sport_key", "")
        score = _score_map_for(sport_key, scores_cache).get((home, away))
        if score is None:
            leg_results.append(None)
            continue
        leg_results.append(resolve_market_result(
            leg.get("market", ""), leg.get("selection", ""),
            home, away, score["home_score"], score["away_score"],
        ))

    if any(r == "loss" for r in leg_results):
        return "loss"
    if any(r is None or r == "manual" for r in leg_results):
        return None  # still pending / needs a leg that can't auto-resolve
    if all(r in ("win", "push") for r in leg_results):
        return "win"
    return None


def _pnl_at_stake(result, odds, stake):
    if result == "win":
        return round(stake * (float(odds) - 1), 2)
    if result == "loss":
        return round(-stake, 2)
    return 0.0  # push


def resolve_pending(stale_days=5):
    entries = load_log()
    pending = [e for e in entries if e.get("result") in (None, "pending")]
    if not pending:
        print("No pending personal bets to resolve.")
        return 0

    scores_cache = {}
    resolved = 0
    today = datetime.now(timezone.utc).date()

    for entry in pending:
        try:
            if entry["type"] == "single":
                result = _resolve_single(entry, scores_cache)
            else:
                result = _resolve_multi(entry, scores_cache)
        except FileNotFoundError as e:
            print(f"  ::warning::{e}")
            continue

        if result is None:
            try:
                days_pending = (today - datetime.strptime(entry["date"], "%Y-%m-%d").date()).days
            except ValueError:
                days_pending = 0
            if days_pending > stale_days:
                entry["result"] = "unresolved"
                entry["pnl"] = None
                print(
                    f"  ::warning::{entry['pick_id']} (tier={entry.get('tier')}) has been pending "
                    f"{days_pending} days with no matching score — marked 'unresolved', needs a "
                    f"manual check against the real result."
                )
                resolved += 1
            continue

        entry["result"] = result
        entry["pnl"] = None if result == "manual" else _pnl_at_stake(result, entry["odds"], entry["stake"])
        resolved += 1
        pnl_str = f"${entry['pnl']:+.2f}" if entry["pnl"] is not None else result
        print(f"  ✅ {entry['pick_id']}: {result.upper()} ({pnl_str})")

    save_log(entries)
    print(f"\nResolved {resolved} personal bet(s).")
    return resolved


def monthly_entries(year_month=None):
    year_month = year_month or datetime.now(timezone.utc).strftime("%Y-%m")
    return [e for e in load_log() if e.get("date", "").startswith(year_month)]


def monthly_summary(year_month=None):
    config = load_config()
    entries = monthly_entries(year_month)
    staked = sum(e["stake"] for e in entries)
    returned = sum(e["stake"] * e["odds"] for e in entries if e.get("result") == "win")
    net = returned - staked
    budget = float(config.get("monthly_budget", 100.00))
    return {
        "year_month": year_month or datetime.now(timezone.utc).strftime("%Y-%m"),
        "staked": round(staked, 2),
        "returned": round(returned, 2),
        "net": round(net, 2),
        "monthly_budget": budget,
        "over_budget_gross": staked > budget,
        "over_budget_net_loss": (-net) > budget,
        "tab_balance": config.get("tab_balance"),
    }


def monthly_summary_lines(year_month=None):
    """Warnings only — per Micah's explicit instruction, nothing here ever
    skips or hides a pick/DM, this just appends a heads-up line."""
    s = monthly_summary(year_month)
    lines = [
        f"Staked: ${s['staked']:.2f}",
        f"Returned: ${s['returned']:.2f}",
        f"Net: ${s['net']:+.2f}",
    ]
    if s["tab_balance"] is not None:
        lines.append(f"TAB balance: ${float(s['tab_balance']):.2f}")
    if s["over_budget_gross"]:
        lines.append(f"⚠️ Gross staked this month (${s['staked']:.2f}) is over your ${s['monthly_budget']:.2f} budget.")
    if s["over_budget_net_loss"]:
        lines.append(f"⚠️ Net loss this month (${-s['net']:.2f}) is over your ${s['monthly_budget']:.2f} budget.")
    return lines


def compare_to_public_record():
    """Rescales the PUBLIC ledger's settled singles (data/picks.json, flat
    $10 stake — see check_results.FLAT_STAKE) down to Micah's own
    single_stake, so 'what the public record did' and 'what I actually did'
    are comparable at the same per-bet stake. pnl scales linearly with stake
    (win: stake*(odds-1), loss: -stake), so this is an exact rescale, not an
    approximation. Multis aren't in data/picks.json at all, so this is
    singles-only on both sides of the comparison."""
    config = load_config()
    scale = float(config["single_stake"]) / PUBLIC_FLAT_STAKE

    if not os.path.exists(PICKS_PATH):
        public_pnl_at_my_scale = 0.0
    else:
        with open(PICKS_PATH) as f:
            public_picks = json.load(f)
        public_pnl_at_my_scale = round(
            sum(p["pnl"] for p in public_picks if p.get("pnl") is not None) * scale, 2
        )

    my_entries = load_log()
    my_staked = round(sum(e["stake"] for e in my_entries), 2)
    my_pnl = round(sum(e["pnl"] for e in my_entries if e.get("pnl") is not None), 2)

    return {
        "my_staked": my_staked,
        "my_pnl": my_pnl,
        "published_record_pnl_at_my_scale": public_pnl_at_my_scale,
    }


def main():
    parser = argparse.ArgumentParser(description="Micah's personal flat-stake bet log.")
    sub = parser.add_subparsers(dest="command", required=True)

    add_p = sub.add_parser("add", help="Log a bet you actually placed.")
    add_p.add_argument("pick_id")
    add_p.add_argument("--tier", choices=list(VALID_TIERS), default=None)

    sub.add_parser("resolve", help="Resolve pending personal bets against real results (nightly).")

    summary_p = sub.add_parser("summary", help="Print this month's staking summary.")
    summary_p.add_argument("--month", default=None, help="YYYY-MM, defaults to the current month.")

    args = parser.parse_args()

    if args.command == "add":
        try:
            add_bet(args.pick_id, tier=args.tier)
        except (FileNotFoundError, ValueError) as e:
            print(f"::error::{e}")
            sys.exit(1)
    elif args.command == "resolve":
        resolve_pending()
    elif args.command == "summary":
        for line in monthly_summary_lines(args.month):
            print(line)
        cmp = compare_to_public_record()
        print(f"\nMy total staked: ${cmp['my_staked']:.2f}")
        print(f"My P&L: ${cmp['my_pnl']:+.2f}")
        print(f"Published record P&L at my stake: ${cmp['published_record_pnl_at_my_scale']:+.2f}")


if __name__ == "__main__":
    main()
