"""
post_instagram_story.py — Posts a single image to the PuntMate NZ Instagram
account as a Story (disappears after 24h).

This mirrors whatever picks card already went out on Telegram, pushed as an
Instagram Story so it shows up in the Stories tray for @puntmatenz.

Two ways this runs:

1. Automatically — .github/workflows/publish.yml calls this script after
   Micah approves a post (same approval gate that already gates the
   Instagram feed post and Facebook post). No action needed day-to-day.

2. Manually / ad-hoc — for one-off posts (e.g. alongside post_r19.py-style
   round posts, which don't go through the automated pipeline):

     cd /Users/reina/Desktop/puntmate
     python3 scripts/post_instagram_story.py data/cards/some_card.png

   Pass a local file (it gets uploaded to catbox.moe for a public URL) or
   a public https:// image URL directly.

Requirements (read from environment / .env):
  IG_USER_ID or INSTAGRAM_USER_ID
      Instagram Business account ID (already set — see PUNTMATE_WORKFLOW.md §7)
  META_PAGE_TOKEN or FACEBOOK_PAGE_TOKEN or INSTAGRAM_ACCESS_TOKEN
      Page access token with instagram_content_publish permission
      (same token already used for the Instagram feed post + Facebook)

No new Meta app, permissions, or app review needed — this reuses the exact
credentials already active for the existing Instagram feed posting.

Known API limitation (not a bug): Instagram Stories published via the Graph
API do NOT support captions, link stickers, polls, or any text overlay —
only the raw image. PuntMate cards already bake in match/pick/odds/branding,
so this isn't a problem for the current design, but keep it in mind if the
image ever changes to something caption-dependent.
"""

import os
import sys
import time
import requests

GRAPH_URL = "https://graph.facebook.com/v21.0"

LAST_ERROR = None  # last Meta API error dict — surfaced into the publish record (2026-07-21)


def _set_last_error(err):
    global LAST_ERROR
    LAST_ERROR = err


def _env(*names):
    """Return the first non-empty environment variable value from the list."""
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


IG_USER_ID = _env("IG_USER_ID", "INSTAGRAM_USER_ID")
IG_TOKEN = _env("META_PAGE_TOKEN", "FACEBOOK_PAGE_TOKEN", "INSTAGRAM_ACCESS_TOKEN")


def upload_to_catbox(image_path):
    """Upload a local image to catbox.moe (free, anonymous) and return the public URL.
    Same hosting approach already used by generate.yml for other platforms."""
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://catbox.moe/user/api.php",
            data={"reqtype": "fileupload"},
            files={"fileToUpload": f},
            timeout=30,
        )
    url = resp.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"catbox.moe upload failed: {url}")
    return url


def post_story_to_instagram(image_url):
    """Publish a single image to Instagram as a Story.
    Returns the published media ID, or None on failure."""
    if not IG_USER_ID or not IG_TOKEN:
        print("  ⚠️  IG_USER_ID / META_PAGE_TOKEN not set — skipping Instagram Story")
        return None

    # Step 1: Create the STORIES media container
    print(f"  → Creating IG Story container for: {image_url}")
    resp = requests.post(
        f"{GRAPH_URL}/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": IG_TOKEN,
        },
        timeout=30,
    )
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG Story container error: {result['error']}")
        _set_last_error(result['error'])
        return None
    container_id = result.get("id")
    print(f"  ✅ Story container created: {container_id}")

    # Step 2: Poll until Meta finishes processing the image (max ~30s)
    status = None
    for _ in range(6):
        time.sleep(5)
        check = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": IG_TOKEN},
            timeout=20,
        ).json()
        status = check.get("status_code")
        print(f"  Container status: {status}")
        if status == "FINISHED":
            break
        if status == "ERROR":
            print(f"  ❌ IG Story container failed processing: {check}")
            return None

    if status != "FINISHED":
        print(f"  ⚠️  Container never confirmed FINISHED (last status: {status}) — trying to publish anyway")

    # Step 3: Publish the Story
    print("  → Publishing Instagram Story...")
    resp = requests.post(
        f"{GRAPH_URL}/{IG_USER_ID}/media_publish",
        data={
            "creation_id": container_id,
            "access_token": IG_TOKEN,
        },
        timeout=30,
    )
    result = resp.json()
    if "error" in result:
        print(f"  ❌ IG Story publish error: {result['error']}")
        _set_last_error(result['error'])
        return None
    media_id = result.get("id")
    print(f"  ✅ Posted Instagram Story: {media_id}")
    return media_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 post_instagram_story.py <path-to-image.png | https://image-url>")
        sys.exit(1)

    arg = sys.argv[1]
    if arg.startswith("http://") or arg.startswith("https://"):
        img_url = arg
    else:
        if not os.path.exists(arg):
            print(f"File not found: {arg}")
            sys.exit(1)
        print("→ Uploading to catbox.moe for a public URL...")
        img_url = upload_to_catbox(arg)
        print(f"  ✅ Public URL: {img_url}")

    media_id = post_story_to_instagram(img_url)
    sys.exit(0 if media_id else 1)
