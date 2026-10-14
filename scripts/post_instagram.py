"""
post_instagram.py — Posts daily picks to Instagram via Graph API.

Supports two post types:
  - Single image post (legacy, falls back if carousel fails)
  - Carousel post (4 slides: intro + one per personality) — preferred

Requirements:
  - INSTAGRAM_USER_ID      : your Instagram Professional account ID
  - INSTAGRAM_ACCESS_TOKEN : long-lived token with instagram_content_publish permission

No image-hosting API key is required: images are hosted either via the
caller-supplied `slide_urls`/`carousel_urls` (the automated pipeline's
already-public raw.githubusercontent.com URLs) or, when posting from a local
file, uploaded anonymously to catbox.moe — the same free, keyless host
post_instagram_story.py already uses. Imgur (which needed IMGUR_CLIENT_ID)
was dropped 2026-10-14 (Item 6): it was the only path here still on a fixed
blind wait before publish and a third-party key for something catbox already
did without one.

Carousel flow:
  1. Upload each slide (to catbox.moe, if no pre-hosted slide_urls given)
  2. Create a media container per slide (IMAGE type, is_carousel_item=true)
  3. Create a CAROUSEL container referencing all slide containers
  4. Poll the carousel container's status_code until FINISHED, then publish
     (2026-10-14, Item 6: replaces a blind time.sleep(5) that published
     before Meta had necessarily finished processing on a slow day)
"""

import os
import requests
import json
import time
from datetime import datetime

from post_instagram_story import upload_to_catbox

IG_USER_ID    = os.environ.get('INSTAGRAM_USER_ID', '')
IG_TOKEN      = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
GRAPH_URL     = "https://graph.facebook.com/v19.0"

# Last Meta API error seen by this module (dict or str), so publish_pick can
# put the REAL reason into the publish record / result email instead of a
# bare ok:False. Added 2026-07-21 after a real failure (OAuthException code
# 190 subcode 467, 'session invalid because the user logged out') was only
# visible by digging through run logs.
LAST_ERROR = None


def _note_error(err):
    global LAST_ERROR
    LAST_ERROR = err
    # Token-death gets an actionable hint right in the record/email.
    try:
        if isinstance(err, dict) and err.get("code") == 190:
            LAST_ERROR = {**err, "fix": "Meta access token invalid/expired — mint a new long-lived Page token and update the META_PAGE_TOKEN GitHub secret."}
    except Exception:
        pass

RESPONSIBLE_LINE = "⚠️ For entertainment & informational purposes only. Not advice. 18+."
HASHTAGS = "#PuntMateNZ #NRL #WorldCup2026 #SportsBetting #NZSports #DailyPicks #ValueBet #SportsTipping"


def _request_with_retry(method, url, max_attempts=3, backoff_base=2, **kwargs):
    """requests.request with retry on transient failures only (timeouts,
    connection errors, 5xx) -- a real Graph API error payload (4xx with an
    "error" body) is a rejection, not a glitch, and is returned immediately
    for the caller to handle. 2026-10-14 (Item 6): the Graph API calls here
    had no retry at all, so a single dropped connection failed the whole
    post for the day."""
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(method, url, timeout=20, **kwargs)
            status = getattr(resp, "status_code", None)
            if isinstance(status, int) and status >= 500 and attempt < max_attempts:
                time.sleep(backoff_base * attempt)
                continue
            return resp
        except requests.RequestException as e:
            last_exc = e
            if attempt < max_attempts:
                time.sleep(backoff_base * attempt)
    raise last_exc


def _poll_container_status(container_id):
    """Poll a media container until Meta reports FINISHED (or ERROR, or we
    give up), mirroring post_instagram_story.py's approach. 2026-10-14 (Item
    6): replaces a blind time.sleep(5)/time.sleep(3) before publish, which
    could fire before Meta had actually finished processing the image on a
    slow day -- polling is both more reliable and usually faster."""
    status = None
    for _ in range(6):
        time.sleep(5)
        check = _request_with_retry(
            "GET", f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
        ).json()
        status = check.get("status_code")
        print(f"  Container status: {status}")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            print(f"  ❌ Container failed processing: {check}")
            return False
    print(f"  ⚠️  Container never confirmed FINISHED (last status: {status}) — trying to publish anyway")
    return True


def _alert_owner(context, err):
    """Immediate private Telegram DM to the owner on a hard Instagram
    publish failure. 2026-10-14 (Item 6): the end-of-run result email
    (email_service.send_result_email) already lists this failure, but it can
    sit unread in an inbox -- this reuses the same instant channel owner_dm.py
    already uses for bet DMs, so a dead token or API error gets noticed the
    same day. Never raises: an alert failure must never affect publishing."""
    try:
        import owner_dm
        owner_dm.send_owner_dm(f"⚠️ PuntMate: Instagram {context} failed.\n{err}")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠️  Owner alert failed to send: {e}")


def _create_ig_container(image_url, caption):
    """Step 1: Create the Instagram media container."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media"
    resp = _request_with_retry("POST", url, data={
        "image_url": image_url,
        "caption": caption,
        "access_token": IG_TOKEN,
    })
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG container error: {result['error']}")
        _note_error(result['error'])
        return None
    container_id = result.get("id")
    print(f"  ✅ IG container created: {container_id}")
    return container_id


def _publish_ig_container(container_id):
    """Step 2: Publish the container."""
    url = f"{GRAPH_URL}/{IG_USER_ID}/media_publish"
    resp = _request_with_retry("POST", url, data={
        "creation_id": container_id,
        "access_token": IG_TOKEN,
    })
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG publish error: {result['error']}")
        _note_error(result['error'])
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
        used to build filenames for logging, and as the catbox.moe upload
        source when slide_urls isn't supplied.
    caption: pre-built caption string (optional — built from picks if not provided)
    picks: list of pick dicts (used to build caption if caption not provided)
    slide_urls: optional list of already-public image URLs (e.g. the
        raw.githubusercontent.com URLs generate.yml commits and hosts). When
        given, skips the upload step entirely and posts these URLs directly —
        this is the path the automated pipeline uses, since the images are
        already public once committed. Falls back to a catbox.moe upload from
        slide_paths only when slide_urls isn't provided (manual/legacy use).
    """
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  IG credentials not set — skipping carousel")
        return False

    if caption is None:
        caption = build_caption(picks or [])

    if slide_urls:
        print(f"  → Using {len(slide_urls)} pre-hosted slide URLs (no upload needed)")
    else:
        # 1. Upload each slide to catbox.moe
        print(f"  → Uploading {len(slide_paths)} slides to catbox.moe...")
        slide_urls = []
        for path in slide_paths:
            try:
                url = upload_to_catbox(path)
            except Exception as e:
                print(f"  ❌ catbox.moe upload failed for {path}: {e}")
                _alert_owner("carousel post", f"image upload failed for {path}: {e}")
                return False
            slide_urls.append(url)

    # 2. Create a media container per slide (carousel items)
    print("  → Creating carousel item containers...")
    item_ids = []
    for i, img_url in enumerate(slide_urls):
        resp = _request_with_retry(
            "POST", f"{GRAPH_URL}/{IG_USER_ID}/media",
            data={
                "image_url": img_url,
                "is_carousel_item": "true",
                "access_token": IG_TOKEN,
            },
        )
        result = resp.json()
        if "error" in result:
            print(f"  ❌ Carousel item {i+1} error: {result['error']}")
            _note_error(result['error'])
            _alert_owner("carousel post", f"slide {i+1} container error: {result['error']}")
            return False
        item_ids.append(result["id"])
        print(f"    ✅ Slide {i+1} container: {result['id']}")

    # 3. Create the CAROUSEL container
    print("  → Creating carousel container...")
    resp = _request_with_retry(
        "POST", f"{GRAPH_URL}/{IG_USER_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
            "access_token": IG_TOKEN,
        },
    )
    result = resp.json()
    if "error" in result:
        print(f"  ❌ Carousel container error: {result['error']}")
        _note_error(result['error'])
        _alert_owner("carousel post", f"carousel container error: {result['error']}")
        return False
    carousel_id = result["id"]
    print(f"  ✅ Carousel container: {carousel_id}")

    # 4. Poll until processed, then publish
    _poll_container_status(carousel_id)
    print("  → Publishing carousel...")
    post_id = _publish_ig_container(carousel_id)
    if post_id:
        print(f"  ✅ Carousel published: {post_id}")
    else:
        _alert_owner("carousel post", f"publish failed after container was created: {LAST_ERROR}")
    return post_id is not None


def post_picks_to_instagram(picks, image_path):
    """Legacy single-image post. Used when carousel slides aren't available."""
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN not set — skipping")
        return False

    if not os.path.exists(image_path):
        print(f"  ❌ Image not found: {image_path}")
        return False

    print("  → Uploading picks card to catbox.moe...")
    try:
        image_url = upload_to_catbox(image_path)
    except Exception as e:
        print(f"  ❌ catbox.moe upload failed: {e}")
        _alert_owner("feed post", f"image upload failed: {e}")
        return False

    caption = build_caption(picks)

    print("  → Creating Instagram media container...")
    container_id = _create_ig_container(image_url, caption)
    if not container_id:
        _alert_owner("feed post", f"container creation failed: {LAST_ERROR}")
        return False

    _poll_container_status(container_id)
    print("  → Publishing to Instagram...")
    post_id = _publish_ig_container(container_id)
    if not post_id:
        _alert_owner("feed post", f"publish failed after container was created: {LAST_ERROR}")
    return post_id is not None


def post_degen_watch_to_instagram(image_path, caption):
    """Single-image post with a caller-supplied caption — unlike
    post_picks_to_instagram, never calls build_caption() (that's the daily
    pick's own caption builder; Degen Watch's caption comes from
    build_review_package.build_degen_watch_text, already validated through
    the strictest responsible-gambling language check). Same
    upload/container/publish flow and LAST_ERROR capture as every other
    path here (2026-10-11, Micah: unofficial no-bet-day content)."""
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  INSTAGRAM_USER_ID or INSTAGRAM_ACCESS_TOKEN not set — skipping")
        return False

    if not os.path.exists(image_path):
        print(f"  ❌ Image not found: {image_path}")
        return False

    print("  → Uploading Degen Watch card to catbox.moe...")
    try:
        image_url = upload_to_catbox(image_path)
    except Exception as e:
        print(f"  ❌ catbox.moe upload failed: {e}")
        _alert_owner("Degen Watch post", f"image upload failed: {e}")
        return False

    print("  → Creating Instagram media container...")
    container_id = _create_ig_container(image_url, caption)
    if not container_id:
        _alert_owner("Degen Watch post", f"container creation failed: {LAST_ERROR}")
        return False

    _poll_container_status(container_id)
    print("  → Publishing to Instagram...")
    post_id = _publish_ig_container(container_id)
    if not post_id:
        _alert_owner("Degen Watch post", f"publish failed after container was created: {LAST_ERROR}")
    return post_id is not None
