"""
owner_dm.py -- private Telegram DM to the account owner for every pick and
weekend multi that PuntMate publishes.

Purpose: the owner follows exactly what PuntMate posts publicly, at a flat
stake (config/my_bets.json). This module NEVER generates, filters or changes a
pick. It reads the same frozen review data the public posts were built from and
sends the owner a one-message summary: the bet, the stake, and where the
month's budget stands.

Hard rules (do not weaken):
  * Public posts are untouched. Staking language lives ONLY in this DM, never
    in public copy, and nothing here goes through (or around) copy_validator.
  * A DM is sent only for a bet whose PUBLIC Telegram post actually succeeded,
    so the owner's record matches what viewers saw.
  * A DM failure can never fail, block or roll back a publish. Everything is
    wrapped; errors are logged as warnings only.
  * Budget warnings are warnings. Nothing is ever skipped or hidden.
  * The only bookmaker reference is TAB_NZ_URL below -- a static link to
    TAB NZ's own homepage (2026-10-12, Micah: wants a one-tap link to place
    the bet himself). Deliberately NOT a pre-filled betslip link: no data
    source covers TAB NZ (checked The Odds API and OpticOdds -- both only
    model TAB Australia/tab.com.au), and tab.co.nz itself blocks automated
    access, so there is no reliable way to derive a per-match or per-selection
    URL. This stays a plain, unchanging homepage link until/unless TAB NZ
    provides real partner/affiliate API access.

Secrets: TELEGRAM_BOT_TOKEN (already used by post_telegram) and OWNER_CHAT_ID.
No personal bet data is written to the repo -- month figures are derived from
the public ledger (data/picks.json), the publish records (data/published/) and
the multi results record (data/multi_results.json).
"""

import json
import os
import re

import requests

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "my_bets.json")
TIERS = ("punter", "gambler", "degenerate")
DEFAULTS = {"single_stake": 2.0, "multi_stake": 5.0, "monthly_budget": 100.0}
TAB_NZ_URL = "https://www.tab.co.nz"


# ── helpers ────────────────────────────────────────────────────────────────

def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    try:
        with open(path) as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return {k: float(cfg[k]) for k in DEFAULTS}


def money(x):
    return f"${x:,.2f}"


def signed(x):
    return f"+${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"


def norm_result(r):
    r = str(r or "").strip().lower()
    if r == "win":
        return "win"
    if r == "loss":
        return "loss"
    if r in ("push", "void"):
        return "push"
    return "open"  # pending / manual / unresolved / unknown


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def multi_text(review_dir, tier):
    path = os.path.join(review_dir, f"{tier}-multi-post.txt")
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return ""


def parse_multi(text):
    """Return (legs, combined_odds) from a published multi post. Legs are the
    '*Leg N:* ...' lines with markdown asterisks removed."""
    legs = [re.sub(r"[*_]", "", ln).strip()
            for ln in text.splitlines() if ln.strip().startswith("*Leg")]
    m = re.search(r"Combined:\s*([\d.]+)", text)
    return legs, (float(m.group(1)) if m else None)


# ── month figures ──────────────────────────────────────────────────────────

def collect_items(month, repo_root=REPO_ROOT, cfg=None):
    """Every PuntMate bet published in `month` (YYYY-MM) whose public Telegram
    post succeeded, as dicts: id, kind, stake, odds, result."""
    cfg = cfg or load_config()
    picks = _read_json(os.path.join(repo_root, "data", "picks.json"), [])
    multi_results = _read_json(os.path.join(repo_root, "data", "multi_results.json"), {})
    items = []
    pub_dir = os.path.join(repo_root, "data", "published")
    if not os.path.isdir(pub_dir):
        return items
    for name in sorted(os.listdir(pub_dir)):
        if not name.endswith(".json"):
            continue
        pick_id = name[:-5]
        pub = _read_json(os.path.join(pub_dir, name), {})
        review_dir = os.path.join(repo_root, "data", "review", pick_id)
        meta = _read_json(os.path.join(review_dir, "post-metadata.json"), {})
        if not str(meta.get("post_date", "")).startswith(month):
            continue
        if meta.get("has_pick") and not meta.get("is_weekend_multi") \
                and (pub.get("telegram") or {}).get("ok") is True:
            row = next((p for p in picks if p.get("date") == meta.get("post_date")
                        and p.get("match") == meta.get("match")), {})
            try:
                odds = float(meta.get("odds"))
            except (TypeError, ValueError):
                odds = None
            items.append({"id": pick_id, "kind": "single", "stake": cfg["single_stake"],
                          "odds": odds, "result": norm_result(row.get("result"))})
        for tier in TIERS:
            if (pub.get(f"telegram_{tier}_multi") or {}).get("ok") is True:
                _, combined = parse_multi(multi_text(review_dir, tier))
                res = (multi_results.get(pick_id) or {}).get(tier)
                items.append({"id": f"{pick_id}:{tier}", "kind": f"{tier} multi",
                              "stake": cfg["multi_stake"], "odds": combined,
                              "result": norm_result(res)})
    return items


def month_stats(items, cfg):
    staked = sum(i["stake"] for i in items)
    settled = [i for i in items if i["result"] != "open"]
    staked_settled = sum(i["stake"] for i in settled)
    returned = 0.0
    for i in settled:
        if i["result"] == "win" and i["odds"]:
            returned += i["stake"] * i["odds"]
        elif i["result"] == "push":
            returned += i["stake"]
    net = returned - staked_settled
    budget = cfg["monthly_budget"]
    warnings = []
    if staked > budget:
        warnings.append(f"Staked {money(staked)} is over your {money(budget)} monthly budget.")
    if -net > budget:
        warnings.append(f"Net loss {money(-net)} is over your {money(budget)} monthly budget.")
    return {"staked": staked, "returned": returned, "net": net, "budget": budget,
            "left": budget - staked, "settled_count": len(settled),
            "open_count": len(items) - len(settled),
            "open_stake": staked - staked_settled, "warnings": warnings}


def with_current(items, current):
    """Add the bet being announced if the month data does not already hold it
    (a multi is only recorded as published AFTER publish() returns)."""
    have = {i["id"] for i in items}
    return items + [c for c in current if c["id"] not in have]


def stats_block(stats):
    lines = [
        "This month (every PuntMate bet at your stakes)",
        f"Staked {money(stats['staked'])} of {money(stats['budget'])} budget "
        f"({money(stats['left']) if stats['left'] >= 0 else 'over by ' + money(-stats['left'])} left)",
        (f"Returned {money(stats['returned'])} | Net {signed(stats['net'])} (settled bets)"
         if stats["settled_count"] else "No settled bets yet this month"),
    ]
    if stats["open_count"]:
        lines.append(f"Still open: {stats['open_count']} bet(s), {money(stats['open_stake'])}")
    lines += [f"WARNING: {w}" for w in stats["warnings"]]
    return "\n".join(lines)


# ── message builders ───────────────────────────────────────────────────────

def _label(s):
    return str(s or "").replace("_", " ").strip().title()


def build_single_dm(meta, cfg, stats):
    odds = float(meta["odds"])
    stake = cfg["single_stake"]
    return "\n".join([
        f"PuntMate pick: follow at {money(stake)}",
        "",
        str(meta.get("match", "")),
        f"{meta.get('selection', '')} ({meta.get('market', '')}) @ {odds:.2f}",
        f"Type: {_label(str(meta.get('bet_type', '')).replace('_BET', ''))} | "
        f"Risk: {_label(meta.get('risk'))} | Confidence: {_label(meta.get('confidence'))}",
        f"Stake {money(stake)} returns {money(stake * odds)} if it wins",
        f"Place it: {TAB_NZ_URL}",
        "",
        stats_block(stats),
    ])


def build_multi_dm(tier, legs, combined, cfg, stats):
    stake = cfg["multi_stake"]
    ret = f"returns {money(stake * combined)} if every leg wins" if combined else "combined odds not found"
    return "\n".join(
        [f"PuntMate {tier.title()} multi: follow at {money(stake)}", ""]
        + (legs or ["(legs not found in the post)"])
        + ["", f"Combined: {combined:.2f}" if combined else "Combined: unknown",
           f"Stake {money(stake)} {ret}", f"Place it: {TAB_NZ_URL}", "", stats_block(stats)]
    )


# ── sending ────────────────────────────────────────────────────────────────

def send_owner_dm(text):
    """Send `text` to OWNER_CHAT_ID. Returns True on success, never raises."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("OWNER_CHAT_ID", "")
    if not token or not chat_id:
        print("  Owner DM: TELEGRAM_BOT_TOKEN / OWNER_CHAT_ID not set -- skipped.")
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat_id, "text": text}, timeout=10)
        ok = bool(r.json().get("ok"))
        if not ok:
            print(f"  Owner DM: Telegram error: {r.text[:200]}")
        return ok
    except Exception as e:  # noqa: BLE001 -- must never break publishing
        print(f"  Owner DM: send failed: {e}")
        return False


def notify(metadata, review_dir, results, platforms, send=send_owner_dm,
           repo_root=REPO_ROOT, dry=False):
    """Send (or, if dry, print) the owner DMs for what was just published.
    `results` is publish()'s results dict; only bets whose public Telegram
    post succeeded get a DM. Returns the list of message texts built."""
    cfg = load_config()
    month = str(metadata.get("post_date", ""))[:7]
    base = collect_items(month, repo_root, cfg)
    pid = metadata.get("pick_id", "")

    def public_ok(key):
        return dry or (results.get(key) or {}).get("ok") is True

    out = []
    if metadata.get("has_pick") and not metadata.get("is_weekend_multi") \
            and "telegram" in platforms and public_ok("telegram"):
        cur = [{"id": pid, "kind": "single", "stake": cfg["single_stake"],
                "odds": float(metadata["odds"]), "result": "open"}]
        out.append(build_single_dm(
            metadata, cfg, month_stats(with_current(base, cur), cfg)))
    for tier in TIERS:
        if not metadata.get(f"has_{tier}_multi") or "telegram" not in platforms \
                or not public_ok(f"telegram_{tier}_multi"):
            continue
        legs, combined = parse_multi(multi_text(review_dir, tier))
        cur = [{"id": f"{pid}:{tier}", "kind": f"{tier} multi", "stake": cfg["multi_stake"],
                "odds": combined, "result": "open"}]
        out.append(build_multi_dm(
            tier, legs, combined, cfg, month_stats(with_current(base, cur), cfg)))

    for text in out:
        if dry:
            print("\n[owner DM -- private Telegram message, DRY RUN]\n" + text)
        else:
            send(text)
    return out
