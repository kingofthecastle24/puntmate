"""
post_telegram.py — Posts picks to PuntMate NZ Telegram channel
Picks are grouped by personality: Investor | Punter | Gambler
"""

import os
import requests
from datetime import datetime

BOT_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = os.environ['TELEGRAM_CHANNEL_ID']

CONFIDENCE_BAR = {
    "High":   "🟢🟢🟢",
    "Medium": "🟡🟡⚪",
    "Low":    "🟡⚪⚪",
}

PERSONALITY_CONFIG = {
    "investor": {
        "label": "INVESTOR",
        "emoji": "📊",
        "tagline": "Low risk. Steady returns. Long game.",
        "header_emoji": "📊📊📊",
    },
    "punter": {
        "label": "PUNTER",
        "emoji": "🎯",
        "tagline": "Back what you know. Trust the form.",
        "header_emoji": "🎯🎯🎯",
    },
    "gambler": {
        "label": "GAMBLER",
        "emoji": "🎰",
        "tagline": "Big odds. Big dreams. No regrets.",
        "header_emoji": "🎰🎰🎰",
    },
}

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
        print(f"  ⚠️  No image to send: {image_path}")
        return None
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as f:
        resp = requests.post(url, data={
            "chat_id": CHANNEL_ID,
            "caption": caption or "PuntMate NZ — Daily Picks",
            "parse_mode": "Markdown",
        }, files={"photo": f}, timeout=30)
    result = resp.json()
    if not result.get('ok'):
        print(f"  ⚠️  Telegram photo error: {result.get('description', result)}")
    else:
        print(f"  ✅ Sent picks card image to Telegram")
    return result


def post_daily_header(pick_count, date_str=None):
    """Post a header message before the personality picks."""
    if not date_str:
        date_str = datetime.now().strftime("%A %-d %B")

    match_count = pick_count // 3 if pick_count >= 3 else pick_count
    text = (
        f"🎯 *PUNTMATE DAILY PICKS*\n"
        f"📅 {date_str}\n\n"
        f"Three personalities. Three angles. {match_count} match{'es' if match_count != 1 else ''}.\n\n"
        f"📊 *Investor* — safe, steady, value-first\n"
        f"🎯 *Punter* — balanced, gut-feel, everyday\n"
        f"🎰 *Gambler* — bold, long shots, big returns\n\n"
        f"{RESPONSIBLE_LINE}"
    )
    _send(text)


def post_personality_block(personality_key, picks):
    """Post all picks for one personality as a single Telegram message."""
    if not picks:
        return

    cfg = PERSONALITY_CONFIG.get(personality_key, {
        "label": personality_key.upper(),
        "emoji": "✅",
        "tagline": "",
        "header_emoji": "✅✅✅",
    })

    lines = [
        f"{cfg['header_emoji']} *{cfg['label']}*",
        f"_{cfg['tagline']}_",
        f"━━━━━━━━━━━━━━",
    ]

    for pick in picks:
        conf = CONFIDENCE_BAR.get(pick.get('confidence', 'Medium'), '⚪⚪⚪')
        lines.append(
            f"\n{pick.get('emoji', cfg['emoji'])} *{pick['sport']}*\n"
            f"⚔️ {pick['match']}\n"
            f"📌 *{pick['pick']}* @ `{pick['odds']}`  {conf}\n"
            f"💬 _{pick['reasoning']}_"
        )

    lines.append(f"\n━━━━━━━━━━━━━━")
    lines.append(f"#PuntMateNZ #{cfg['label']}")

    _send("\n".join(lines))
    print(f"  ✅ Posted {cfg['label']} block ({len(picks)} pick(s))")


def post_all_picks(picks):
    """
    Group picks by personality and post one block per personality.
    Order: Investor → Punter → Gambler
    """
    grouped = {"investor": [], "punter": [], "gambler": []}
    for pick in picks:
        key = pick.get("personality", "punter")
        if key in grouped:
            grouped[key].append(pick)

    for personality_key in ["investor", "punter", "gambler"]:
        personality_picks = grouped[personality_key]
        if personality_picks:
            post_personality_block(personality_key, personality_picks)


def post_no_picks():
    """Post a message when no picks are found."""
    text = (
        "📭 No standout picks today — sometimes the best bet is no bet.\n\n"
        "Back tomorrow with fresh picks. 🤙\n\n"
        "#PuntMateNZ"
    )
    _send(text)


# Legacy single-pick function (kept for compatibility)
def post_pick(pick):
    """Post a single pick. Deprecated — use post_all_picks() instead."""
    personality_key = pick.get("personality", "punter")
    post_personality_block(personality_key, [pick])
