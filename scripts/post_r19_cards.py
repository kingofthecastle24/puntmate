#!/usr/bin/env python3
"""PuntMate — Argentina vs Egypt World Cup R16 pick"""
import sys, os
sys.path.insert(0, "scripts")

from generate_picks_image import generate_carousel
import requests

OUT = "data/cards"
os.makedirs(OUT, exist_ok=True)

FOOTER = "R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz"
TG_BOT  = os.environ["TG_BOT"]
TG_CHAN  = os.environ["TG_CHAN"]
FB_TOKEN = os.environ.get("FB_TOKEN", "")
FB_PAGE  = os.environ.get("FB_PAGE", "")
NL = "\n"

single = {
    "match": "Argentina vs Egypt",
    "home_team": "Argentina",
    "away_team": "Egypt",
    "selection": "Argentina to Win",
    "odds": "1.40",
    "market": "Head to Head",
    "sport_label": "FIFA World Cup 2026",
    "sport_tag": "FOOTBALL",
    "cover_theme": "Banker of the Day",
    "analysis": "Messi has scored 7 in this tournament. Egypt scraped through on penalties against Australia. Argentina built for knockout football and will sort themselves out and win with class.",
    "confidence": 4,
    "riskTagline": "LOW RISK · INVESTOR PLAY · BACK THE CLASS",
    "big_game": True,
}

print("Generating card...")
spaths = generate_carousel(single, OUT)
print("Card:", spaths[0])

def tg_photo(path, caption):
    with open(path, "rb") as f:
        r = requests.post(
            "https://api.telegram.org/bot" + TG_BOT + "/sendPhoto",
            data={"chat_id": TG_CHAN, "caption": caption, "parse_mode": "Markdown"},
            files={"photo": f}, timeout=30)
    j = r.json()
    print("TG photo ok:", j.get("ok"), j.get("description", ""))
    return j

def tg_text(text):
    r = requests.post(
        "https://api.telegram.org/bot" + TG_BOT + "/sendMessage",
        json={"chat_id": TG_CHAN, "text": text, "parse_mode": "Markdown"},
        timeout=30)
    j = r.json()
    print("TG text ok:", j.get("ok"), j.get("description", ""))
    return j

def fb_photo(path, caption):
    if not FB_TOKEN or not FB_PAGE:
        print("FB skipped (no token)"); return
    with open(path, "rb") as f:
        ir = requests.post("https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            files={"image": f}, timeout=30)
    ij = ir.json()
    if not ij.get("success"):
        print("Imgur failed:", ij.get("data", {})); return
    img_url = ij["data"]["link"]
    r = requests.post(
        "https://graph.facebook.com/v21.0/" + FB_PAGE + "/photos",
        data={"url": img_url, "caption": caption, "access_token": FB_TOKEN}, timeout=30)
    j = r.json()
    print("FB", j.get("id"), j.get("error", ""))

banker_caption = (
    "\U0001f3af *ARGENTINA TO WIN @ 1.40 | WORLD CUP R16*" + NL +
    "Messi's scored 7 in this tournament. Egypt scraped through on pens. Back the class." + NL +
    "_" + FOOTER + "_"
)
fb_caption = banker_caption.replace("*", "").replace("_", "")

print("\nPosting to Telegram...")
tg_photo(spaths[0], banker_caption)

print("\nPosting to Facebook...")
fb_photo(spaths[0], fb_caption)

print("\nDone!")
