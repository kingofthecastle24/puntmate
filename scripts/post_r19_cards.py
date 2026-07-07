import os
import requests
from generate_picks_image import generate_carousel

# --- Pick Data ---
single = {
    'match': 'Argentina vs Egypt',
    'home_team': 'Argentina',
    'away_team': 'Egypt',
    'selection': 'Argentina to Win',
    'odds': '1.40',
    'market': 'Head to Head',
    'sport_label': 'FIFA World Cup 2026',
    'sport_tag': 'FOOTBALL',
    'cover_theme': 'Banker of the Day',
    'analysis': "Messi has scored 7 in this tournament. Egypt scraped through on penalties against Australia. Argentina built for knockout football — sort themselves out and win with class.",
    'confidence': 4,
    'riskTagline': 'LOW RISK · INVESTOR PLAY · BACK THE CLASS',
    'big_game': True,
}

picks = [single]

# --- Generate carousel image ---
image_path = generate_carousel(picks)
print(f"Image generated: {image_path}")

# --- Telegram ---
TELEGRAM_TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
TELEGRAM_CHAT_ID = os.environ['TELEGRAM_CHAT_ID']

tg_caption = (
    "🎯 *ARGENTINA TO WIN @ 1.40 | WORLD CUP R16*\n"
    "Messi's scored 7 in this tournament. Egypt scraped through on pens. Back the class.\n"
    "_R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz_"
)

with open(image_path, 'rb') as f:
    tg_resp = requests.post(
        f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto',
        data={
            'chat_id': TELEGRAM_CHAT_ID,
            'caption': tg_caption,
            'parse_mode': 'Markdown',
        },
        files={'photo': f}
    )

print(f"Telegram: {tg_resp.status_code}", tg_resp.json())

# --- Facebook ---
FB_PAGE_TOKEN = os.environ['FB_PAGE_ACCESS_TOKEN']
FB_PAGE_ID = os.environ['FB_PAGE_ID']

fb_caption = (
    "🎯 ARGENTINA TO WIN @ 1.40 | WORLD CUP R16\n"
    "Messi's scored 7 in this tournament. Egypt scraped through on pens. Back the class.\n\n"
    "R18 | Gamble responsibly | 0800 654 655 | gamblinghelpline.co.nz"
)

with open(image_path, 'rb') as f:
    fb_resp = requests.post(
        f'https://graph.facebook.com/{FB_PAGE_ID}/photos',
        data={
            'caption': fb_caption,
            'access_token': FB_PAGE_TOKEN,
        },
        files={'source': f}
    )

print(f"Facebook: {fb_resp.status_code}", fb_resp.json())
