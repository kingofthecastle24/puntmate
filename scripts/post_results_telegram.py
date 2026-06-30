"""
post_results_telegram.py — Posts a results update to the PuntMate NZ Telegram channel.
Run after check_results.py resolves any pending picks.
"""

import json
import os
import requests

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

REPO_ROOT = os.path.join(os.path.dirname(__file__), '..')
PICKS_PATH = os.path.join(REPO_ROOT, 'data', 'picks.json')


def post_results():
    if not os.path.exists(PICKS_PATH):
        print("No picks.json found")
        return

    with open(PICKS_PATH, 'r') as f:
        all_picks = json.load(f)

    # Recently settled picks (non-pending, non-manual)
    settled = [p for p in all_picks if p['result'] in ('win', 'loss', 'push')]
    if not settled:
        print("No settled picks to report")
        return

    # Find picks settled today (result just changed from pending)
    # We post all settled picks from the last check — detect by date proximity
    # For simplicity, show last 5 settled picks as "recent results"
    recent = sorted(settled, key=lambda p: p['date'], reverse=True)[:5]

    wins_all = sum(1 for p in settled if p['result'] == 'win')
    losses_all = sum(1 for p in settled if p['result'] == 'loss')
    pnl_all = sum(p['pnl'] for p in settled if p['pnl'] is not None)

    # Build recent results lines
    result_lines = []
    for p in recent:
        icon = "✅" if p['result'] == 'win' else "❌"
        pnl_str = f"${p['pnl']:+.2f}" if p['pnl'] is not None else ""
        result_lines.append(f"{icon} {p['match']}\n   ↳ {p['pick']} @ {p['odds']} {pnl_str}")

    results_block = "\n\n".join(result_lines)

    pnl_emoji = "📈" if pnl_all >= 0 else "📉"
    message = (
        f"📊 *PUNTMATE RESULTS UPDATE*\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"{results_block}\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"*All-time record:* {wins_all}W / {losses_all}L\n"
        f"*All-time P&L:* {pnl_emoji} `${pnl_all:+.2f}` _(${10:.0f} flat stake)_\n\n"
        f"_All analysis is for entertainment only. Bet responsibly — Problem Gambling Foundation NZ: 0800 664 262_"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }, timeout=10)

    result = resp.json()
    if result.get('ok'):
        print(f"✅ Results posted to Telegram")
    else:
        print(f"❌ Telegram error: {result}")


if __name__ == "__main__":
    post_results()
