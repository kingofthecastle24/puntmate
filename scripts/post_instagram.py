"""
post_instagram.py — Posts the daily picks card to Instagram via Graph API.

Requirements:
  - INSTAGRAM_USER_ID  : your Instagram Professional account ID
  - INSTAGRAM_ACCESS_TOKEN : a long-lived token with instagram_content_publish permission
  - The picks image must be publicly accessible (we upload to Imgur or use a GitHub raw URL)

Flow:
  1. Upload picks card image to Imgur (free, no auth needed for anonymous upload)
     OR serve via GitHub raw URL (slower but no extra service)
  2. Create an Instagram media container
  3. Publish the container

Note: Instagram does not allow text-only posts — an image is always required.
"""

import os
import requests
import json
import time
from datetime import datetime

IG_USER_ID    = os.environ.get('INSTAGRAM_USER_ID', '')
IG_TOKEN      = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
IMGUR_CLIENT  = os.environ.get('IMGUR_CLIENT_ID', '')  # optional — for image hosting
GRAPH_URL     = "https://graph.facebook.com/v19.0"

RESPONSIBLE_LINE = "⚠️ Bet responsibly. Problem Gambling Foundation NZ: 0800 664 262"
HASHTAGS = "#PuntMateNZ #NRL #FIFA #WorldCup2026 #SportsBetting #NZSports #DailyPicks #Investor #Punter #Gambler"


def _upload_to_imgur(image_path):
    """Upload image to Imgur and return the public URL."""
    if not IMGUR_CLIENT:
        print("  ⚠️  No IMGUR_CLIENT_ID set — skipping Imgur upload")
        return None
    with open(image_path, 'rb') as f:
        resp = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": f"Client-ID {IMGUR_CLIENT}"},
            files={"image": f},
            timeout=30,
        )
    data = resp.json()
    if data.get("success"):
        url = data["data"]["link"]
        print(f"  ✅ Uploaded to Imgur: {url}")
        return url
    print(f"  ❌ Imgur upload failed: {data}")
    return None


def _create_ig_container(image_url, caption):
    """Step 1: Create the Instagram media container."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    resp = requests.post(url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": IG_TOKEN,
    }, timeout=20)
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG container error: {result['error']}")
        return None
    container_id = result.get("id")
    print(f"  ✅ IG container created: {container_id}")
    return container_id


def _publish_ig_container(container_id):
    """Step 2: Publish the container."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media_publish"
    resp = requests.post(url, data={
        "creation_id": container_id,
        "access_token": IG_TOKEN,
    }, timeout=20)
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG publish error: {result['error']}")
        return None
    post_id = result.get("id")
    print(f"  ✅ Posted to Instagram: {post_id}")
    return post_id


def build_caption(picks, date_str=None):
    """Build the Instagram caption text."""
    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")

    grouped = {"investor": [], "punter": [], "gambler": []}
    for p in picks:
        key = p.get("personality", "punter")
        if key in grouped:
            grouped[key].append(p)

    lines = [
        f"🎯 PUNTMATE DAILY PICKS — {date_str}",
        "",
        "Three personalities. Three angles. One winner.",
        "",
    ]

    emoji_map = {"investor": "📊", "punter": "🎯", "gambler": "🎰"}
    for key in ["investor", "punter", "gambler"]:
        if grouped[key]:
            p = grouped[key][0]  # first pick per personality for caption
            lines.append(f"{emoji_map[key]} {key.upper()}: {p['pick']} @ {p['odds']} — {p['match']}")

    lines += [
        "",
        RESPONSIBLE_LINE,
        "",
        HASHTAGS,
    ]
    return "\n".join(lines)


def post_picks_to_instagram(picks, image_path):
    """Main function: upload image + post to Instagram."""
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN not set — skipping")
        return False

    if not os.path.exists(image_path):
        print(f"  ❌ Image not found: {image_path}")
        return False

    print("  → Uploading picks card to Imgur...")
    image_url = _upload_to_imgur(image_path)
    if not image_url:
        print("  ⚠️  No image URL — skipping Instagram post")
        return False

    caption = build_caption(picks)

    print("  → Creating Instagram media container...")
    container_id = _create_ig_container(image_url, caption)
    if not container_id:
        return False

    # Instagram requires a short wait before publishing
    time.sleep(3)

    print("  → Publishing to Instagram...")
    post_id = _publish_ig_container(container_id)
    return post_id is not None
