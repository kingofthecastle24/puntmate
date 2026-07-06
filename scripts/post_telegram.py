"""
post_telegram.py — Posts picks to Puntmate NZ Telegram channel.
Value betting pipeline: one message per pick, no personality grouping.
"""

import os
import requests
from datetime import datetime

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

RESPONSIBLE_LINE = "_All analysis is for entertainment only. Bet responsibly — Problem Gambling Foundation NZ: 0800 664 262_"


def _send(text, parse_mode="Markdown"):
    """Send a message to the Telegram channel."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": parse_mode,
    }, timeout=10)
    result = resp.json()
    if not result.get('ok'):
        print(f"  Telegram error: {result}")
    return result


def post_text(text, parse_mode="Markdown"):
    """Public wrapper — send plain text to the channel."""
    return _send(text, parse_mode=parse_mode)


def send_picks_card(image_path, caption=None):
    """Send the picks card image to the Telegram channel."""
    if not image_path or not os.path.exists(image_path):
        print(f"  Warning: No image to send: {image_path}")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as f:
        resp = requests.post(url, data={
            "chat_id": CHANNEL_ID,
            "caption": caption or "Puntmate NZ — Daily Picks",
            "parse_mode": "Markdown",
        }, files={"photo": f}, timeout=30)
    result = resp.json()
    if not result.get('ok'):
        print(f"  Warning: Telegram photo error: {result.get('description', result)}")
    else:
        print(f"  Sent picks card image to Telegram")
    return result


def post_no_picks():
    """Post a message when no value picks are found."""
    text = (
        "No value picks today — sometimes the best bet is no bet.\n\n"
        "Back when there's genuine edge.\n\n"
        "#PuntmateNZ"
    )
    _send(text)
