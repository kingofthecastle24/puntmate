#!/usr/bin/env python3
"""
owner_dm.py — sends Micah a private Telegram DM mirroring every official
pick/multi PuntMate actually published, plus a running month-to-date stake
summary from my_bets.py.

Never regenerates copy: reads the exact frozen
data/review/<pick_id>/post-metadata.json the public post was built from —
the same file publish_pick.py itself reads. Deliberately independent of
workflow_state/manifest and of publish_pick.py's own result tracking — a
failure here must never affect the public PUBLISHED/PARTIALLY_PUBLISHED
state, and this never gates (or is gated by) the public publish succeeding.

Staking language is allowed here (private DM only) — see
copy_validator.py's module docstring for why it's banned in public copy;
that gate is untouched by this module, and this text is never run through
it.

No DM on a No-Bet/Watchlist day — gated on has_pick / has_{tier}_multi,
the same flags publish_pick.py itself keys off.
"""
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from build_review_package import _combined_odds

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
OWNER_CHAT_ID = os.environ.get("OWNER_CHAT_ID", "")

MULTI_TIER_LABELS = {"punter": "PUNTER", "gambler": "GAMBLER", "degenerate": "DEGENERATE"}


def build_single_dm(metadata, stake):
    lines = [
        "🔒 PRIVATE — YOUR PICK",
        f"{metadata.get('sport_label', '')} — {metadata.get('match', '')}",
        "",
        f"PICK: {metadata.get('selection', '')}",
        f"ODDS: {metadata.get('odds', '')} ({metadata.get('market', '')})",
        # bet_type_label already carries a "BET TYPE: " prefix (see
        # generate_pick.BET_TYPE_LABELS) — only add our own when falling
        # back to the raw bet_type, so it never doubles up.
        metadata.get("bet_type_label") or f"BET TYPE: {metadata.get('bet_type', '')}",
        f"RISK: {metadata.get('risk', '')}",
        f"CONFIDENCE: {metadata.get('confidence_label', metadata.get('confidence', ''))}",
        "",
        f"Stake: ${stake:.2f}",
    ]
    return "\n".join(lines)


def build_multi_dm(tier, legs, stake):
    label = MULTI_TIER_LABELS.get(tier, tier.upper())
    lines = [f"🔒 PRIVATE — YOUR {label} MULTI", ""]
    for i, leg in enumerate(legs, 1):
        lines.append(f"Leg {i}: {leg['match']} — {leg['selection']} @ {leg['odds']} ({leg['market']})")
    combined = _combined_odds(legs)
    lines += [
        "",
        f"Combined odds: {combined:.2f}",
        f"Stake: ${stake:.2f}",
    ]
    return "\n".join(lines)


def _send(text):
    if DRY_RUN:
        print("DRY RUN — owner DM that WOULD be sent:")
        print("-" * 55)
        print(text)
        print("-" * 55)
        return {"ok": True, "dry_run": True}
    if not BOT_TOKEN or not OWNER_CHAT_ID:
        print("  ::warning::owner_dm: TELEGRAM_BOT_TOKEN or OWNER_CHAT_ID not set — skipping.")
        return {"ok": False, "skipped": True}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": OWNER_CHAT_ID, "text": text}, timeout=10)
        result = resp.json()
    except Exception as e:
        print(f"  owner_dm send error: {e}")
        return {"ok": False, "error": str(e)}
    if not result.get("ok"):
        print(f"  owner_dm Telegram error: {result}")
    return result


def main():
    pick_id = os.environ.get("PICK_ID", "").strip()
    if not pick_id:
        print("No PICK_ID — nothing to DM.")
        return

    meta_path = os.path.join(REVIEW_ROOT, pick_id, "post-metadata.json")
    if not os.path.exists(meta_path):
        print(f"No post-metadata.json for {pick_id} — nothing to DM.")
        return
    with open(meta_path) as f:
        metadata = json.load(f)

    try:
        from my_bets import load_config, monthly_summary_lines
        config = load_config()
        summary_footer = "\n\n— This month —\n" + "\n".join(monthly_summary_lines())
    except Exception as e:
        print(f"  ::warning::owner_dm: could not load my_bets config/summary ({e}) — using defaults, no summary footer.")
        config = {"single_stake": 2.00, "multi_stake": 5.00}
        summary_footer = ""

    sent_any = False

    if metadata.get("has_pick"):
        text = build_single_dm(metadata, config.get("single_stake", 2.00)) + summary_footer
        _send(text)
        sent_any = True

    for tier in ("punter", "gambler", "degenerate"):
        if metadata.get(f"has_{tier}_multi"):
            legs = metadata.get(f"{tier}_multi_legs") or []
            if not legs:
                print(f"  ::warning::owner_dm: has_{tier}_multi is true but {tier}_multi_legs is empty — skipping DM for this tier.")
                continue
            text = build_multi_dm(tier, legs, config.get("multi_stake", 5.00)) + summary_footer
            _send(text)
            sent_any = True

    if not sent_any:
        print(f"{pick_id}: no pick or multi to DM (No-Bet/Watchlist day) — staying silent.")


if __name__ == "__main__":
    main()
