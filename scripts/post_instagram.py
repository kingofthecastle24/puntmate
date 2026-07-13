"""
post_instagram.py — Posts daily picks to Instagram via Graph API.

Supports two post types:
  - Single image post (legacy, falls back if carousel fails)
  - Carousel post (4 slides: intro + one per personality) — preferred

Requirements:
  - INSTAGRAM_USER_ID      : your Instagram Professional account ID
  - INSTAGRAM_ACCESS_TOKEN : long-lived token with instagram_content_publish permission
  - IMGUR_CLIENT_ID        : free Imgur API key for image hosting

Carousel flow:
  1. Upload each slide to Imgur
  2. Create a media container per slide (IMAGE type, is_carousel_item=true)
  3. Create a CAROUSEL container referencing all slide containers
  4. Wait 5s then publish the carousel
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
HASHTAGS = "#PuntMateNZ #NRL #WorldCup2026 #SportsBetting #NZSports #DailyPicks #ValueBet #SportsTipping"


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
    """Build the Instagram caption for value betting picks."""
    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")

    tier_emoji = {"investor": "📊", "punter": "🎯", "gambler": "🎰"}

    lines = [
        f"🏆 PUNTMATE VALUE PICKS — {date_str}",
        "",
    ]

    for p in picks:
        tier = p.get("tier", "punter").lower()
        emoji = tier_emoji.get(tier, "🎯")
        lines.append(f"{emoji} {p.get('sport_label', '')} | {p.get('selection', '')} @ {p.get('odds', '')}")
        lines.append(f"   {p.get('insight', '')}")
        lines.append("")

    lines += [
        "Swipe for the full breakdown 👆",
        "Follow @puntmatenz for daily value picks",
        "",
        RESPONSIBLE_LINE,
        "",
        HASHTAGS,
    ]
    return "\n".join(lines)


def post_carousel_to_instagram(slide_paths, caption=None, picks=None, slide_urls=None):
    """
    Post a carousel to Instagram.
    slide_paths: list of local image file paths (cover, tip, breakdown) — only
        used to build filenames for logging, and as the Imgur upload source
        when slide_urls isn't supplied.
    caption: pre-built caption string (optional — built from picks if not provided)
    picks: list of pick dicts (used to build caption if caption not provided)
    slide_urls: optional list of already-public image URLs (e.g. the
        raw.githubusercontent.com URLs generate.yml commits and hosts). When
        given, skips the Imgur upload entirely and posts these URLs directly —
        this is the path the automated pipeline uses, since the images are
        already public once committed. Falls back to Imgur upload from
        slide_paths only when slide_urls isn't provided (manual/legacy use).
    """
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  IG credentials not set — skipping carousel")
        return False

    if caption is None:
        caption = build_caption(picks or [])

    if slide_urls:
        print(f"  → Using {len(slide_urls)} pre-hosted slide URLs (no Imgur upload needed)")
    else:
        # 1. Upload each slide to Imgur
        print(f"  → Uploading {len(slide_paths)} slides to Imgur...")
        slide_urls = []
        for path in slide_paths:
            url = _upload_to_imgur(path)
            if not url:
                print(f"  ❌ Imgur upload failed for {path}")
                return False
            slide_urls.append(url)

    # 2. Create a media container per slide (carousel items)
    print("  → Creating carousel item containers...")
    item_ids = []
    for i, img_url in enumerate(slide_urls):
        resp = requests.post(
            f"{GRAPH_URL}/{IG_USER_ID}/media",
            data={
                "image_url": img_url,
                "is_carousel_item": "true",
                "access_token": IG_TOKEN,
            },
            timeout=20,
        )
        result = resp.json()
        if "error" in result:
            print(f"  ❌ Carousel item {i+1} error: {result['error']}")
            return False
        item_ids.append(result["id"])
        print(f"    ✅ Slide {i+1} container: {result['id']}")

    # 3. Create the CAROUSEL container
    print("  → Creating carousel container...")
    resp = requests.post(
        f"{GRAPH_URL}/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": IG_TOKEN,
        },
        timeout=20,
    )
    result = resp.json()
    if "error" in result:
        print(f"  ❌ Carousel container error: {result['error']}")
        return False
    carousel_id = result["id"]
    print(f"  ✅ Carousel container: {carousel_id}")

    # 4. Wait and publish
    time.sleep(5)
    print("  → Publishing carousel...")
    post_id = _publish_ig_container(carousel_id)
    if post_id:
        print(f"  ✅ Carousel published: {post_id}")
    return post_id is not None


def post_picks_to_instagram(picks, image_path):
    """Legacy single-image post. Used when carousel slides aren't available."""
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

    time.sleep(3)
    print("  → Publishing to Instagram...")
    post_id = _publish_ig_container(container_id)
    return post_id is not None
