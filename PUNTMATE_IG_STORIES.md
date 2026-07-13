# PuntMate NZ — Instagram Story Mirroring

*Added: July 2026. Companion to `PUNTMATE_WORKFLOW.md` — read that first for the full pipeline.*

## What this is

Every approved picks post now also goes out as an Instagram Story (24h,
disappearing) on `@puntmatenz`, automatically. Facebook is untouched —
it was explicitly out of scope for this change and nothing about how it
posts has changed.

## Status: fully automated, no setup needed

Good news: this didn't need a new Meta app, new permissions, or app
review. `PUNTMATE_WORKFLOW.md` already documents that Instagram is fully
linked (`IG_USER_ID`, `META_PAGE_TOKEN` with `instagram_content_publish`) —
that's the same permission Stories publishing uses, just with
`media_type=STORIES` instead of the default feed image type. Since the
existing Instagram feed post was already live and working, Stories needed
zero new credentials.

## How it triggers

Same trigger and same approval gate as everything else on Instagram —
nothing changed about *when* Instagram gets posted to, only *what* gets
posted:

1. `generate.yml` runs (cron or manual), posts to Telegram immediately,
   builds `data/social_post.json` (image + caption), commits it.
2. **Micah approves** in the GitHub Actions `production` environment gate
   — same as today.
3. `publish.yml` runs. It now does three things instead of two:
   - Posts the feed photo to Instagram (unchanged)
   - **Posts the same image as an Instagram Story (new)**
   - Posts to Facebook (unchanged)

The Story uses the same `image_url` from `data/social_post.json` that's
already used for the Instagram feed post and Facebook — no new image
generation, no new hosting step.

**Why gate the Story on the same approval instead of firing the instant
Telegram posts?** Telegram is the only channel that posts un-gated today;
Instagram and Facebook were both deliberately built to wait for Micah's
review. Mirroring the Story at that same approval point keeps that
intentional design — nothing new goes to Instagram without a human
looking at it first. If you'd rather the Story fire the moment Telegram
does (bypassing approval), that's a small change to make, but it means
Instagram could post before you've had a chance to review the pick — say
so and I'll wire it differently.

## What was built

| File | What it does |
|------|--------------|
| `scripts/post_instagram_story.py` | New. Publishes a single image to Instagram as a Story via the Graph API (`media_type=STORIES`). Also usable standalone for ad-hoc posts. |
| `.github/workflows/publish.yml` | Edited. Added a "Post to Instagram Story" step, right after the existing "Post to Instagram" step. Reuses `IG_USER_ID` / `META_PAGE_TOKEN` secrets — no new secrets added. |

No changes were made to `scripts/post_facebook.py`, the Facebook step in
`publish.yml`, `scripts/main.py`'s Telegram posting, or any Facebook
secrets/config.

## Manual / ad-hoc posting

For one-off posts outside the automated pipeline (e.g. alongside a
`post_r19.py`-style manual round post, which doesn't touch Instagram at
all), run the new script directly:

```bash
cd /Users/reina/Desktop/puntmate
python3 scripts/post_instagram_story.py data/cards/2026-07-06_Storm_vs_Titans_night_1_cover.png
```

It uploads the local file to catbox.moe (same free host `generate.yml`
already uses) to get a public URL, then posts it as a Story. You can also
pass a public `https://` URL directly if you already have one.

This reads credentials from your local `.env` (falls back through
`META_PAGE_TOKEN` → `FACEBOOK_PAGE_TOKEN` → `INSTAGRAM_ACCESS_TOKEN`, and
`IG_USER_ID` → `INSTAGRAM_USER_ID`) — same as the rest of the local
scripts. Nothing new to add there either.

**Note:** `post_r19.py`-style manual scripts are Telegram-only and won't
auto-trigger a Story — that's a deliberate limitation (they're one-off
scripts you edit by hand each time), not a bug. Run the command above
alongside them if you want a Story for a manual post too.

## Known limitations (Meta's API, not this implementation)

- **No caption on the Story.** The Graph API does not support captions,
  link stickers, polls, or any text overlay for Stories published this
  way — only the raw image. This isn't a real problem here since the
  picks cards already bake in the match, pick, odds, and branding
  directly into the image. If you ever want a "swipe up" / link sticker
  on the Story, that's a separate, more limited part of the API and
  would need investigation.
- **Aspect ratio.** PuntMate cards are 1080×1350 (4:5), not Instagram's
  recommended 9:16 (1080×1920) for Stories. Instagram will still accept
  and display it — it just gets letterboxed (bars above/below) instead of
  filling the full Story frame. `PUNTMATE_WORKFLOW.md`'s roadmap already
  flags a dedicated 1080×1920 Story template (`_draw_story_*` functions in
  `generate_picks_image.py`) as a future nice-to-have — that would remove
  the letterboxing but is a separate, larger piece of work than this
  mirroring feature.
- **Shared rate limit.** Stories count toward the same 25-posts/24h Graph
  API cap as feed posts and Reels. At 1–2 picks/day this isn't close to
  being an issue.
- **Token expiry.** The Story step uses the same `META_PAGE_TOKEN` as
  everything else, which expires ~60 days per `PUNTMATE_WORKFLOW.md`
  §6/§11. When that token is refreshed, the Story posting keeps working
  automatically — no separate token to manage.

## What still needs Micah's input

Nothing, to get this working as-is. It'll run on the very next approved
post.

Two things worth a decision, not a blocker:

1. **Timing** — confirm you're happy with the Story firing at the same
   approval-gated point as the Instagram feed post, not the instant
   Telegram fires (see "How it triggers" above).
2. **Dedicated 9:16 Story template** — worth doing at some point so the
   Story fills the screen properly instead of being letterboxed, but not
   needed for this to work today.

## Separate findings (not part of this task, flagging anyway)

Two things noticed while reading through the repo — worth a look, not
something I touched:

1. **`.env.example` has a real-looking Facebook Page access token
   hardcoded in it** (not the placeholder `XXXX` pattern that
   `.env.template` uses, and — unlike `.env` — not covered by
   `.gitignore`, since the pattern only matches `.env` / `*.env`, not
   `.env.example`). If this file has ever been committed and pushed to
   GitHub, that token should be treated as compromised and rotated via
   the Graph API Explorer (see `PUNTMATE_WORKFLOW.md` §6 "Refresh the
   token").

2. **The git remote URL has a GitHub personal access token embedded in
   it** (`https://ghp_...@github.com/...`), stored in plaintext in local
   git config. That token currently has push access to the repo from
   this machine. Worth moving to SSH or a credential helper instead of
   an embedded token, and rotating it if there's any doubt about who's
   had access to this machine.

Neither of these was touched or investigated further — just flagging
since they came up while reading the repo for this task.
