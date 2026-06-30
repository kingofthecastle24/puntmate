"""
post_results_telegram.py — Posts a results update to the PuntMate NZ Telegram channel.
Run after check_results.py resolves any pending picks.
Shows per-personality breakdown: Investor / Punter / Gambler.
"""

import json
import os
import requests

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')

PERSONALITY_CONFIG = {
    "investor": {"label": "Investor", "emoji": "📊"},
    "punter":   {"label": "Punter",   "emoji": "🎯"},
    "gambler":  {"label": "Gambler",  "emoji": "🎰"},
}


def _send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown"
    }, timeout=10)
    result = resp.json()
    if not result.get('ok'):
        print(f"Telegram error: {result}")
    return result


def _personality_stats(picks, personality_key):
    settled = [p for p in picks if p.get('personality') == personality_key
               and p['result'] in ('win', 'loss', 'push')]
    wins = sum(1 for p in settled if p['result'] == 'win')
    losses = sum(1 for p in settled if p['result'] == 'loss')
    pnl = sum(p['pnl'] for p in settled if p['pnl'] is not None)
    return wins, losses, pnl, len(settled)


def post_results():
    if not os.path.exists(PICKS_PATH):
        print("No picks.json found")
        return

    with open(PICKS_PATH, 'r') as f:
        all_picks = json.load(f)

    settled = [p for p in all_picks if p['result'] in ('win', 'loss', 'push')]
    if not settled:
        print("No settled picks to report")
        return

    # Recent results (last 6 settled — 2 per personality roughly)
    recent = sorted(settled, key=lambda p: p['date'], reverse=True)[:6]

    # Recent result lines
    result_lines = []
    for p in recent:
        cfg = PERSONALITY_CONFIG.get(p.get('personality', 'punter'), {"emoji": "✅", "label": ""})
        icon = "✅" if p['result'] == 'win' else "❌"
        pnl_str = f"${p['pnl']:+.2f}" if p['pnl'] is not None else ""
        result_lines.append(
            f"{icon} {cfg['emoji']} {p['match']}\n"
            f"   ↳ {p['pick']} @ {p['odds']} {pnl_str}"
        )

    # Per-personality totals
    personality_lines = []
    total_pnl = 0
    for key in ["investor", "punter", "gambler"]:
        cfg = PERSONALITY_CONFIG[key]
        w, l, pnl, n = _personality_stats(all_picks, key)
        if n > 0:
            sign = "📈" if pnl >= 0 else "📉"
            personality_lines.append(
                f"{cfg['emoji']} *{cfg['label']}:* {w}W/{l}L  {sign} `${pnl:+.2f}`"
            )
            total_pnl += pnl

    results_block = "\n\n".join(result_lines)
    personality_block = "\n".join(personality_lines)
    total_sign = "📈" if total_pnl >= 0 else "📉"

    message = (
        f"📊 *PUNTMATE RESULTS*\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"{results_block}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"*All-time by personality:*\n"
        f"{personality_block}\n\n"
        f"*Combined P&L:* {total_sign} `${total_pnl:+.2f}` _($10 flat stake)_\n\n"
        f"_All analysis is for entertainment only. Bet responsibly — Problem Gambling Foundation NZ: 0800 664 262_"
    )

    _send(message)
    print("✅ Results posted to Telegram")


if __name__ == "__main__":
    post_results()
