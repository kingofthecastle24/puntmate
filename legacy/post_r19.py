"""
post_r19.py — Round 19 picks post script
Posts Storm banker + home treble multi to Telegram

# ── TELEGRAM POSTING PATTERN ────────────────────────────────────────────────
# Always send ONLY slide 1 (the cover card, i.e. spaths[0]) as the photo.
# Put the full pick explanation in the caption — not a short tagline.
#
# Caption format:
#   🎯 *[SELECTION] @ [ODDS] | [SPORT/ROUND]*
#   [Full analysis — 2-3 sentences from single['analysis']]
#   _Odds indicative only. Confirm with your betting provider._
#   _R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz_
# ────────────────────────────────────────────────────────────────────────────
"""

import os, sys, requests

# Load env from .env file
env = {}
script_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(script_dir)
env_path = os.path.join(project_dir, '.env')

with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

BOT_TOKEN = env['TELEGRAM_BOT_TOKEN']
CHANNEL_ID = env['TELEGRAM_CHANNEL_ID']
CARDS_DIR = os.path.join(project_dir, 'data', 'cards')

DISCLAIMER = "_Odds indicative only. Confirm with your betting provider._"
FOOTER = "_R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz_"


def send_photo(image_path, caption):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as f:
        resp = requests.post(url, data={
            "chat_id": CHANNEL_ID,
            "caption": caption,
            "parse_mode": "Markdown",
        }, files={"photo": f}, timeout=30)
    result = resp.json()
    if result.get('ok'):
        print(f"  ✅ Sent: {os.path.basename(image_path)}")
    else:
        print(f"  ❌ Error: {result.get('description', result)}")
    return result


def send_text(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": "Markdown",
    }, timeout=10)
    result = resp.json()
    if result.get('ok'):
        print(f"  ✅ Text message sent")
    else:
        print(f"  ❌ Error: {result.get('description', result)}")
    return result


print("🚀 PuntMate NZ — Round 19 Picks Post")
print("=" * 40)

# --- 1. Banker pick: Storm to Win ---
# Cover card only (slide 1). Full analysis in caption.
print("\n📸 Posting banker card (Storm cover)...")
banker_card = os.path.join(CARDS_DIR, "2026-07-06_Storm_vs_Titans_night_1_cover.png")
banker_analysis = (
    "Melbourne Storm are the class side in the competition and have been dominant at home this season. "
    "Titans have struggled to cause upsets on the road, and Storm's defensive structure makes them hard to beat. "
    "Banker play — minimal risk at the price."
)
banker_msg = (
    f"🎯 *STORM TO WIN @ 1.40 | NRL R19*\n"
    f"{banker_analysis}\n"
    f"{DISCLAIMER}\n"
    f"{FOOTER}"
)
send_photo(banker_card, banker_msg)

# --- 2. Multi: Home treble ---
# Cover card only (slide 1). Full analysis in caption.
print("\n📸 Posting multi cover card...")
multi_card = os.path.join(CARDS_DIR, "2026-07-06_multi_1_cover.png")
multi_analysis = (
    "Three home sides — Storm, Warriors, and Dolphins — all backed at odds between 1.40 and 1.52. "
    "Each is individually a strong play; combined they return a solid price on what should be a reliable weekend of results. "
    "Storm 1.40 + Warriors 1.40 + Dolphins 1.52 = *$2.98*."
)
multi_msg = (
    f"🎯 *HOME TREBLE @ $2.98 | NRL R19*\n"
    f"{multi_analysis}\n"
    f"{DISCLAIMER}\n"
    f"{FOOTER}"
)
send_photo(multi_card, multi_msg)

print("\n✅ Round 19 posts complete!")
