"""
post_facebook.py — Posts to the PuntMate NZ Facebook PAGE via Graph API.

HISTORY / why this was rewritten (2026-07-19): the original version of this
module was built for the retired three-personality format, and a real live
post on 2026-07-14 failed with "(#200) The permission(s) publish_actions are
not available. It has been deprecated." — see
data/published/2026-07-14_France_vs_Spain.json. That error means the request
was made with a USER access token: publish_actions (user-timeline posting)
is indeed dead, but posting AS A PAGE never was. It needs a PAGE access
token with the pages_manage_posts + pages_read_engagement permissions.
After that failure, publish_pick.py stopped calling Facebook entirely and
reported "expected via linked Instagram account" — but Meta does NOT
auto-share API-published Instagram content to a linked Facebook Page (the
in-app "Share to Facebook" toggle only applies to posts made in the
Instagram app), so in practice nothing ever reached Facebook. Confirmed by
Micah 2026-07-19: the Page is linked and still gets no posts.

Required environment:
  FACEBOOK_PAGE_ID     — the Page's numeric ID (Page → About → Page ID,
                         or GET /me/accounts with your user token)
  FACEBOOK_PAGE_TOKEN  — a PAGE access token (falls back to META_PAGE_TOKEN
                         if unset, since that token may already be
                         page-scoped from the Instagram setup)

To mint a Page token: Graph API Explorer → your app → get a user token with
pages_manage_posts + pages_read_engagement → GET /me/accounts → copy the
page's "access_token". Exchange for a long-lived one via
/oauth/access_token?grant_type=fb_exchange_token.

All functions return the created object's id on success, None on failure —
never raise, so one platform's failure can't take down another's publish.
"""

import os
import requests

PAGE_TOKEN = os.environ.get("FACEBOOK_PAGE_TOKEN", "") or os.environ.get("META_PAGE_TOKEN", "")
PAGE_ID = os.environ.get("FACEBOOK_PAGE_ID", "")
GRAPH_URL = "https://graph.facebook.com/v19.0"


def is_configured():
    """True when both a Page ID and a token are present — publish_pick uses
    this to report Facebook as 'skipped' (not 'failed') until Micah adds the
    FACEBOOK_PAGE_ID secret, so an unconfigured Page doesn't mark every run
    PARTIALLY_PUBLISHED."""
    return bool(PAGE_ID and PAGE_TOKEN)


def _configured():
    if not PAGE_ID or not PAGE_TOKEN:
        print(
            "  Facebook: FACEBOOK_PAGE_ID and a page token (FACEBOOK_PAGE_TOKEN "
            "or META_PAGE_TOKEN) are required — skipping. Add FACEBOOK_PAGE_ID "
            "in GitHub → Settings → Secrets and variables → Actions."
        )
        return False
    return True


def _explain_error(err):
    """Print the Graph error plus, for the known permission failures, the
    exact fix — so a failed run's log tells Micah what to do, instead of a
    bare OAuthException."""
    print(f"  Facebook error: {err}")
    msg = str(err.get("message", "")).lower()
    if "publish_actions" in msg or err.get("code") in (200, 190, 10):
        print(
            "  -> This means the token is a USER token or lacks Page "
            "permissions. Facebook Page posting needs a PAGE access token "
            "with pages_manage_posts. Get one: Graph API Explorer -> user "
            "token with pages_manage_posts -> GET /me/accounts -> use that "
            "page access_token as the FACEBOOK_PAGE_TOKEN secret."
        )


def _call(endpoint, data):
    url = f"{GRAPH_URL}/{PAGE_ID}/{endpoint}"
    try:
        resp = requests.post(url, data={**data, "access_token": PAGE_TOKEN}, timeout=20)
        result = resp.json()
    except Exception as e:
        print(f"  Facebook request failed: {e}")
        return None
    if "error" in result:
        _explain_error(result["error"])
        return None
    return result


def post_photo(image_url, caption):
    """Photo post on the Page feed from a public image URL (the same
    Imgur-hosted card URLs the Instagram publish already uses)."""
    if not _configured():
        return None
    result = _call("photos", {"url": image_url, "caption": caption})
    if result:
        post_id = result.get("post_id") or result.get("id")
        print(f"  Posted photo to Facebook Page: {post_id}")
        return post_id
    return None


def post_text(message):
    """Plain text post on the Page feed — fallback when no card URL exists."""
    if not _configured():
        return None
    result = _call("feed", {"message": message})
    if result:
        print(f"  Posted to Facebook Page feed: {result.get('id')}")
        return result.get("id")
    return None


def post_story(photo_url):
    """Page Story from a public image URL. Two-step: upload the photo
    unpublished, then attach it to a story."""
    if not _configured():
        return None
    upload = _call("photos", {"url": photo_url, "published": "false"})
    if not upload or not upload.get("id"):
        return None
    story = _call("photo_stories", {"photo_id": upload["id"]})
    if story:
        story_id = story.get("post_id") or story.get("id")
        print(f"  Posted Story to Facebook Page: {story_id}")
        return story_id
    return None
