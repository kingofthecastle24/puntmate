"""
post_telegram.py — Posts picks to PuntMate NZ Telegram channel
"""

import os
import requests
from datetime import datetime

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

CONFIDENCE_BAR = {
    "High":   "🟢🟢🟢 HIGH",
    "Medium": "🟡🟡⚪ MEDIUM",
    "Low":    "🟡⚪⚪ SPECCY",
}


def post_pick(pick):
    """Post a single pick to Telegram channel."""
    conf = CONFIDENCE_BAR.get(pick.get('confidence', 'Medium'), '⚪⚪⚪')

    message = (
        f"{pick.get('emoji', '✅')} *PUNTMATE PICK*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🏆 {pick['sport']}\n"
        f"⚔️ {pick['match']}\n\n"
        f"📌 *{pick['pick']}* @ `{pick['odds']}`\n"
        f"📊 Confidence: {conf}\n\n"
        f"💬 _{pick['reasoning']}_\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔗 Free picks daily — share with your mates\n"
        f"#PuntMateNZ #{pick['sport'].split()[0].replace('🌍','').replace('🏉','').replace('🏀','').strip()}"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    response = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }, timeout=10)

    result = response.json()
    if result.get('ok'):
        print(f"  ✅ Posted to Telegram: {pick['match']}")
    else:
        print(f"  ❌ Telegram error: {result}")
    return result


def post_daily_header(pick_count, date_str=None):
    """Post a header message before the picks."""
    if not date_str:
        date_str = datetime.now().strftime("%A %-d %B")

    message = (
        f"🎯 *PUNTMATE DAILY PICKS*\n"
        f"📅 {date_str}\n\n"
        f"Found {pick_count} pick{'s' if pick_count != 1 else ''} today 👇\n\n"
        f"_All analysis is for entertainment. Bet responsibly — TAB NZ problem gambling: 0800 654 655_"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": message,
        "parse_mode": "Markdown"
    }, timeout=10)


def post_no_picks():
    """Post a message when no picks are found."""
    message = (
        "📭 No standout value picks today — sometimes the best bet is no bet.\n\n"
        "Back tomorrow with fresh picks. 🤙\n\n"
        "#PuntMateNZ"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": message
    }, timeout=10)
