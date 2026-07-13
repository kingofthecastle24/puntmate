#!/usr/bin/env python3
"""
PuntMate NZ — Brand Font Downloader
Run: python3 ~/Desktop/puntmate/download_fonts.sh
Downloads all 9 required TTFs into ./fonts/
"""

import urllib.request
import re
import os
import sys

FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
os.makedirs(FONTS_DIR, exist_ok=True)

# Old browser UA forces Google Fonts to return TTF instead of woff2
TTF_UA = "Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; SV1)"

# Each entry: (Google Fonts API URL, output filename)
# One request per weight — avoids Google only returning first variant
FONTS = [
    ("https://fonts.googleapis.com/css2?family=Archivo:wght@900&display=swap",             "Archivo-Black.ttf"),
    ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400&display=swap",       "SpaceGrotesk-Regular.ttf"),
    ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500&display=swap",       "SpaceGrotesk-Medium.ttf"),
    ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@700&display=swap",       "SpaceGrotesk-Bold.ttf"),
    ("https://fonts.googleapis.com/css2?family=Space+Mono:wght@400&display=swap",          "SpaceMono-Regular.ttf"),
    ("https://fonts.googleapis.com/css2?family=Space+Mono:wght@700&display=swap",          "SpaceMono-Bold.ttf"),
    ("https://fonts.googleapis.com/css2?family=Anton&display=swap",                        "Anton-Regular.ttf"),
    ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600&display=swap",    "BarlowCondensed-SemiBold.ttf"),
    ("https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&display=swap",    "BarlowCondensed-Bold.ttf"),
]

url_re = re.compile(r"url\((https://fonts\.gstatic\.com/[^\)]+)\)")

print(f"Downloading {len(FONTS)} fonts to {FONTS_DIR}/\n")

downloaded = 0
for api_url, filename in FONTS:
    dest = os.path.join(FONTS_DIR, filename)

    if os.path.exists(dest) and os.path.getsize(dest) > 1000:
        print(f"  ✓ {filename} (already exists)")
        downloaded += 1
        continue

    # Step 1: fetch CSS to get the actual font file URL
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": TTF_UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            css = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  ✗ {filename} — CSS fetch failed: {e}")
        continue

    urls = url_re.findall(css)
    if not urls:
        print(f"  ✗ {filename} — no font URL found in CSS")
        continue

    font_url = urls[0]  # take first (latin subset)

    # Step 2: download the font file
    try:
        req = urllib.request.Request(font_url, headers={"User-Agent": TTF_UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        with open(dest, "wb") as f:
            f.write(data)
        kb = len(data) // 1024
        print(f"  ↓ {filename} ({kb}kb)")
        downloaded += 1
    except Exception as e:
        print(f"  ✗ {filename} — download failed: {e}")

print(f"\n{downloaded}/{len(FONTS)} fonts ready.")
if downloaded == len(FONTS):
    print("All done — fonts are in puntmate/fonts/")
