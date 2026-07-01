"""
post_facebook.py — Posts picks to PuntMate NZ Facebook Page via Graph API.
Requires FACEBOOK_PAGE_TOKEN and FACEBOOK_PAGE_ID environment variables.
Same pick structure as post_telegram.py.
"""

import os
import requests
from datetime import datetime

PAGE_TOKEN = os.environ.get('FACEBOOK_PAGE_TOKEN', '')
PAGE_ID    = os.environ.get('FACEBOOK_PAGE_ID', '')
GRAPH_URL  = "https://graph.facebook.com/v19.0"

PERSONALITY_CONFIG = {
    "investor": {"label": "INVESTOR 📊", "tagline": "Low risk. Steady returns. Long game."},
    "punter":   {"label": "PUNTER 🎯",   "tagline": "Back what you know. Trust the form."},
    "gambler":  {"label": "GAMBLER 🎰",  "tagline": "Big odds. Big dreams. No regrets."},
}

RESPONSIBLE_LINE = "⚠️ All analysis is for entertainment only. Bet responsibly — Problem Gambling Foundation NZ: 0800 664 262"


def _post(message):
    """Post a message to the Facebook Page feed."""
    url = f"{GRAPH_URL}/{PAGE_ID}/feed"
    resp = requests.post(url, data={
        "message": message,
        "access_token": PAGE_TOKEN,
    }, timeout=15)
    result = resp.json()
    if "error" in result:
        print(f"  ❌ Facebook error: {result['error']}")
        return None
    print(f"  ✅ Posted to Facebook: {result.get('id')}")
    return result.get("id")


def post_daily_header(pick_count, date_str=None):
    """Post the daily header."""
    if not date_str:
        date_str = datetime.now().strftime("%A %-d %B")

    match_count = pick_count // 3 if pick_count >= 3 else pick_count
    message = (
        f"🎯 PUNTMATE DAILY PICKS — {date_str}\n\n"
        f"Three personalities. Three angles. {match_count} match{'es' if match_count != 1 else ''} today.\n\n"
        f"📊 Investor — safe, steady, value-first\n"
        f"🎯 Punter — balanced, gut-feel, everyday\n"
        f"🎰 Gambler — bold, long shots, big returns\n\n"
        f"👇 See the picks below\n\n"
        f"{RESPONSIBLE_LINE}"
    )
    return _post(message)


def post_personality_block(personality_key, picks):
    """Post all picks for one personality as a single Facebook post."""
    if not picks:
        return

    cfg = PERSONALITY_CONFIG.get(personality_key, {
        "label": personality_key.upper(),
        "tagline": "",
    })

    lines = [
        f"{'━' * 20}",
        f"{cfg['label']}",
        f"{cfg['tagline']}",
        f"{'━' * 20}",
    ]

    for pick in picks:
        lines.append(
            f"\n🏆 {pick['sport']}"
            f"\n⚔️  {pick['match']}"
            f"\n📌 Pick: {pick['pick']} @ {pick['odds']}"
            f"\n💬 {pick['reasoning']}"
        )

    lines.append(f"\n#PuntMateNZ #{cfg['label'].split()[0]}")

    _post("\n".join(lines))


def post_all_picks(picks):
    """Group picks by personality and post one block per personality."""
    grouped = {"investor": [], "punter": [], "gambler": []}
    for pick in picks:
        key = pick.get("personality", "punter")
        if key in grouped:
            grouped[key].append(pick)

    for personality_key in ["investor", "punter", "gambler"]:
        if grouped[personality_key]:
            post_personality_block(personality_key, grouped[personality_key])


def post_no_picks():
    """Post a no-picks message."""
    _post(
        "📭 No standout value picks today — sometimes the best bet is no bet.\n\n"
        "Back tomorrow with fresh picks. 🤙\n\n"
        "#PuntMateNZ"
    )


def post_results(picks_data):
    """Post a results update with per-personality breakdown."""
    settled = [p for p in picks_data if p['result'] in ('win', 'loss', 'push')]
    if not settled:
        return

    recent = sorted(settled, key=lambda p: p['date'], reverse=True)[:6]
    lines = ["📊 PUNTMATE RESULTS UPDATE", "━" * 20, ""]

    for p in recent:
        icon = "✅" if p['result'] == 'win' else "❌"
        cfg = PERSONALITY_CONFIG.get(p.get('personality', 'punter'), {"label": ""})
        pnl_str = f"${p['pnl']:+.2f}" if p['pnl'] is not None else ""
        lines.append(f"{icon} {p['match']}\n   ↳ {p['pick']} @ {p['odds']} {pnl_str}")

    lines.append(f"\n{'━' * 20}")
    total_pnl = sum(p['pnl'] for p in settled if p['pnl'] is not None)
    wins = sum(1 for p in settled if p['result'] == 'win')
    losses = sum(1 for p in settled if p['result'] == 'loss')
    sign = "📈" if total_pnl >= 0 else "📉"
    lines.append(f"All-time: {wins}W / {losses}L  {sign} ${total_pnl:+.2f} ($10 flat stake)")
    lines.append(f"\n{RESPONSIBLE_LINE}")

    _post("\n".join(lines))
