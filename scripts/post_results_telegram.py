"""
post_results_telegram.py — nightly results update for the Telegram channel.
Runs in check_results.yml after check_results.py settles pending picks.

REWRITTEN 2026-07-19 (fresh-record reset): the old version was legacy
three-personality code — it posted "All-time by personality" P&L built from
the ENTIRE ledger (which would contradict the fresh public record every
night) and included "$10 flat stake" wording, i.e. staking language that
copy_validator bans from every other public surface. This version:
  - respects config/record_start_date (same cutoff as the weekly recap)
  - groups by bet_type (Investor/Punter/Gambler tiers), not the retired
    "personality" field
  - shows W-L and strike rate only — no dollar amounts, no stake language
  - validates the message with copy_validator before sending, like every
    other public post
"""

import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(__file__))
from copy_validator import validate_text, CopyValidationError

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')
RECORD_START_PATH = os.path.join(REPO_ROOT, 'config', 'record_start_date')

TIER_LABELS = {
    "INVESTOR_BET": ("📊", "Investor"),
    "PUNTER_BET": ("🎯", "Punter"),
    "GAMBLER_BET": ("🎰", "Gambler"),
}
RESPONSIBLE_LINE = "R18 · Gamble responsibly · Problem Gambling Foundation NZ: 0800 664 262"


def record_start_date():
    if not os.path.exists(RECORD_START_PATH):
        return None
    with open(RECORD_START_PATH) as f:
        return f.read().strip() or None


def load_record_picks():
    if not os.path.exists(PICKS_PATH):
        return []
    with open(PICKS_PATH) as f:
        picks = json.load(f)
    cutoff = record_start_date()
    if cutoff:
        picks = [p for p in picks if p.get("date", "") >= cutoff]
    return picks


def strike_rate(w, l):
    return f"{round(100 * w / (w + l))}%" if (w + l) else "—"


def build_results_text(picks):
    """Returns the message text, or None when there's nothing to post."""
    settled = [p for p in picks if p.get("result") in ("win", "loss", "push")]
    if not settled:
        return None

    recent = sorted(settled, key=lambda p: p.get("date", ""), reverse=True)[:5]
    result_lines = []
    for p in recent:
        icon = "✅" if p["result"] == "win" else "➖" if p["result"] == "push" else "❌"
        result_lines.append(f"{icon} {p.get('match', '')}\n   ↳ {p.get('pick', '')} @ {p.get('odds', '')}")

    wins = sum(1 for p in settled if p["result"] == "win")
    losses = sum(1 for p in settled if p["result"] == "loss")

    tier_lines = []
    for bt, (emoji, label) in TIER_LABELS.items():
        rows = [p for p in settled if p.get("bet_type") == bt]
        w = sum(1 for p in rows if p["result"] == "win")
        l = sum(1 for p in rows if p["result"] == "loss")
        if w + l:
            tier_lines.append(f"{emoji} *{label}:* {w}W–{l}L ({strike_rate(w, l)})")

    parts = [
        "📊 *PUNTMATE RESULTS*",
        "━━━━━━━━━━━━━━",
        "",
        "\n\n".join(result_lines),
        "",
        f"*Record: {wins}W–{losses}L · Strike rate {strike_rate(wins, losses)}*",
    ]
    if tier_lines:
        parts.append("\n".join(tier_lines))
    parts += ["", "Every result on the record, wins and losses alike.", "", RESPONSIBLE_LINE]
    return "\n".join(parts)


def _send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
    }, timeout=10)
    return resp.json()


def post_results():
    text = build_results_text(load_record_picks())
    if text is None:
        print("No settled picks on the fresh record yet — nothing to post.")
        return
    try:
        validate_text(text, risk="STANDARD_PICK", public=True)
    except CopyValidationError as e:
        print(f"::error::results post failed copy validation — refusing to post: {e}")
        raise SystemExit(1)
    _send(text)
    print("Results posted to Telegram")


if __name__ == "__main__":
    post_results()
