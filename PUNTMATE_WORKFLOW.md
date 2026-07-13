# PuntMate NZ — Master Workflow Reference

*Last updated: July 2026 · Brand Kit v2*

This document covers everything about how PuntMate NZ operates: what the system is, how it's wired together, and exactly what to change when something needs updating. Written for someone picking it up cold.

---

## Table of Contents

1. [What PuntMate NZ Is](#1-what-puntmate-nz-is)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Automated Pipeline — Full Flow](#3-automated-pipeline--full-flow)
4. [Pick Research & Value Engine](#4-pick-research--value-engine)
5. [Card Design System](#5-card-design-system)
6. [Platform Publishing Specs](#6-platform-publishing-specs)
7. [GitHub Secrets Reference](#7-github-secrets-reference)
8. [GitHub Actions Workflows](#8-github-actions-workflows)
9. [Manual Posting (Ad-hoc)](#9-manual-posting-ad-hoc)
10. [Results Tracking](#10-results-tracking)
11. [How to Tweak Things](#11-how-to-tweak-things)
12. [Costs & API Usage](#12-costs--api-usage)
13. [Roadmap / Planned Features](#13-roadmap--planned-features)

---

## 1. What PuntMate NZ Is

PuntMate NZ is an automated sports betting picks service for NZ audiences. It posts daily value picks to Telegram and Facebook, with Instagram planned.

**Channels:**
- Telegram: `@puntmatenz` — primary channel, image + analysis
- Facebook Page: PuntMate NZ (Page ID: `1173598642506628`)
- Instagram: `@puntmatenz` — Business account linked to Facebook Page (IG User ID: `17841415246709818`)

**Target audience:** NZ males 18–45. Sports betting-aware. Uses TAB NZ / Betcha.

**Sports covered:**
- NRL (core NZ audience, Warriors following)
- FIFA World Cup 2026 (live now — major opportunity)
- Super Rugby Pacific
- UFC/MMA
- Wimbledon ATP/WTA

**Brand:** Black background (`#0B0F0D`), rotating neon accents (green/blue/amber/pink), premium editorial feel. Two visual themes: *Betslip Night* (everyday) and *Matchday Print* (big games/finals).

**Philosophy:** Value betting only — finding where the bookmaker has mispriced the market. Edge % = our estimated true probability minus the bookmaker's implied probability. No pick if edge < 7%. Silence is better than a forced post.

---

## 2. System Architecture Overview

Three independent layers. No AI tokens are spent on card generation or posting.

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — INTELLIGENCE                                  │
│  Claude Sonnet 4.6 (claude-sonnet-4-6)                   │
│  · Fetches odds via The Odds API                         │
│  · Runs value analysis (implied prob vs true estimate)   │
│  · Generates pick JSON + Telegram caption                │
│  Runs inside: GitHub Actions (generate.yml)              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — CARD GENERATION                               │
│  Python / Pillow (zero AI tokens)                        │
│  scripts/generate_picks_image.py                         │
│  · Renders 1080×1350px PNG carousels (3 slides/pick)     │
│  · Two themes: Betslip Night + Matchday Print            │
│  · Supersampled at 2× then downscaled (LANCZOS)          │
│  · Output: data/cards/*.png                              │
│  Runs inside: GitHub Actions (same generate job)         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  LAYER 3 — PUBLISHING                                    │
│  Python / requests (zero AI tokens)                      │
│  · Telegram: sendPhoto + sendMessage APIs                │
│  · Facebook: /photos endpoint (image via catbox.moe URL) │
│  · Instagram: Meta Content Publishing API (2-step)       │
│  Runs inside: GitHub Actions (publish.yml)               │
│  Gated by Micah's approval (GitHub Environment)          │
└─────────────────────────────────────────────────────────┘
```

**Key files:**

| File | Purpose |
|------|---------|
| `scripts/main.py` | Pipeline orchestrator — runs steps 1–7 |
| `scripts/fetch_odds.py` | Pulls live odds from The Odds API |
| `scripts/generate_pick.py` | Value analysis via Claude Sonnet 4.6 |
| `scripts/generate_picks_image.py` | Renders PNG carousel cards (Pillow) |
| `scripts/post_telegram.py` | Posts to Telegram channel |
| `scripts/post_facebook.py` | Posts to Facebook Page |
| `scripts/post_instagram.py` | Posts to Instagram (carousel) |
| `scripts/log_picks.py` | Appends picks to `data/picks.json` ledger |
| `scripts/check_results.py` | Resolves PENDING picks with scores |
| `scripts/post_results_telegram.py` | Posts results summary to Telegram |
| `scripts/post_r19.py` | One-off manual post script (ad-hoc use) |
| `data/picks.json` | Permanent picks ledger (all-time record) |
| `data/latest_run.json` | Today's run output (overwritten each run) |
| `data/social_post.json` | Caption + image URL committed by generate.yml for publish.yml to read |
| `data/cards/*.png` | Generated card images |

---

## 3. Automated Pipeline — Full Flow

### Triggers

`generate.yml` runs on two cron schedules:

| Cron | NZT time | Purpose |
|------|----------|---------|
| `0 20 * * *` | 8:00am daily | Morning picks |
| `0 6 * * 5,6,0` | 6:00pm Fri/Sat/Sun | Evening game coverage |

Also triggerable manually: GitHub → Actions tab → "PuntMate Social — Generate & Approve" → Run workflow.

### Step-by-step

**Job 1: `generate` (GitHub Actions — ubuntu-latest)**

1. **Checkout repo** — gets latest main
2. **Install dependencies** — `pip install -r requirements.txt` (anthropic, requests, cairosvg, Pillow)
3. **Download fonts** — Archivo Black, Space Grotesk Medium/Bold, Space Mono Regular/Bold pulled from Google Fonts CDN at runtime (not committed to repo)
4. **Run `scripts/main.py`** — with Telegram secrets only (Facebook/Instagram skipped here, handled by publish.yml)
   - Fetches odds → value analysis → generates PNG cards → posts to Telegram
5. **Run `scripts/log_picks.py`** — reads `data/latest_run.json`, appends to `data/picks.json`
6. **Upload card to catbox.moe** — finds the most recent PNG in `data/cards/`, uploads anonymously to catbox.moe, gets a public HTTPS URL (required because Meta's Graph API needs a publicly accessible image)
7. **Build caption + save `data/social_post.json`** — constructs brand caption from pick data, writes `{"image_url": ..., "caption": ..., "post_date": ...}` to `data/social_post.json`
8. **Commit to main** — commits `data/picks.json`, `data/latest_run.json`, `data/social_post.json` with message `chore: prepare social post YYYY-MM-DD [skip ci]`

**Job 2: `approve` (approval gate)**

Pauses on the `production` GitHub Environment. Micah reviews picks in the GitHub Actions UI and clicks Approve. This gates publication — nothing goes to Facebook/Instagram until approved.

Setup: Settings → Environments → `production` → Required reviewers → add GitHub username.

**`publish.yml` (triggered by `generate.yml` completion)**

Runs automatically when `generate.yml` succeeds (i.e. Micah approved). Can also be triggered manually for retries.

1. **Post to Instagram** — reads `data/social_post.json`, creates media container (`POST /{ig_user_id}/media`), waits 5s, publishes container. Skipped if `IG_USER_ID` secret is not set.
2. **Post to Facebook** — posts to `/{page_id}/photos` with `image_url` from catbox.moe. Falls back to text-only `/feed` post if no image URL.

**`check_results.yml` (daily at 11pm NZT)**

Cron: `0 11 * * *` (UTC). Runs ~15hrs after morning picks — enough time for most games to finish.

1. **`scripts/check_results.py`** — reads `data/picks.json`, fetches scores via The Odds API `/scores` endpoint, resolves PENDING picks to win/loss/push, calculates P&L ($10 flat stake)
2. **`scripts/post_results_telegram.py`** — posts per-personality results summary to Telegram
3. Commits resolved `data/picks.json` back to main

---

## 4. Pick Research & Value Engine

### Data source

The Odds API (free tier, 500 requests/month, ~2–3/day actual usage).

API key: `ODDS_API_KEY` in GitHub Secrets.

Region: `au` (covers Australian/NZ bookmakers including TAB).

Markets: `h2h` (head-to-head only).

Sports pulled (in priority order):
```python
SPORTS = [
    "soccer_fifa_world_cup",
    "rugbyleague_nrl",
    "rugbyunion_super_rugby",
    "mma_mixed_martial_arts",
    "tennis_atp_wimbledon",
    "tennis_wta_wimbledon",
]
```

Only matches kicking off within the next 24 hours are considered.

### Value analysis (generate_pick.py)

Model: `claude-sonnet-4-6`

System prompt role: "PuntMate NZ — a sharp sports analyst whose job is value betting." Returns structured JSON only.

**Algorithm:**

1. For each match, calculate bookmaker's implied probability (accounting for overround):
   ```
   raw = 1 / odds
   total = sum of all raw values
   implied = raw / total
   ```
2. Claude estimates true probability using sports knowledge, form, context
3. Edge = true probability − implied probability
4. Minimum edge threshold: **7%** — any pick below this is discarded
5. Returns 1–2 best picks (if nothing clears 7%, posts nothing and stays silent)

**Edge → Confidence mapping:**

| Edge % | Dots | Label | Risk Tagline |
|--------|------|-------|-------------|
| ≥20% | 5/5 | HIGH | STRONG VALUE |
| ≥14% | 4/5 | HIGH | CLEAR EDGE |
| ≥10% | 3/5 | MODERATE | SOLID VALUE |
| ≥7% | 2/5 | MODERATE | GOOD VALUE |
| <7% | — | — | Not posted |

**Pick tiers:**

| Tier | Meaning | Odds range | Frequency |
|------|---------|-----------|-----------|
| `investor` | High confidence, bookmaker clearly wrong | Usually <2.50 | Daily primary |
| `punter` | Good value, moderate confidence | Any | Several/week |
| `gambler` | Big edge at big odds — high variance | High | Max once/week |

Tier is set by Claude's analysis, not forced. If the best pick is gambler-tier, only post that one — don't manufacture an investor pick to fill a slot.

**Big game detection:**

FIFA World Cup and UFC/MMA events automatically trigger the Matchday Print visual theme. NRL Warriors finals, All Blacks tests, and any match with "Final", "Grand Final", "Championship" etc. in the team names also trigger it.

### Accent rotation

The Betslip Night theme rotates through four accent colours across posts to prevent visual repetition:

```
green (#35E07E) → blue (#3DB2FF) → amber (#FFC145) → pink (#FF4FA3) → repeat
```

State is saved in `data/last_post_meta.json` between runs.

---

## 5. Card Design System

Script: `scripts/generate_picks_image.py`

### Technical specs

| Property | Value |
|----------|-------|
| Output size | 1080 × 1350px (4:5 portrait) |
| Render size | 2160 × 2700px (2× supersampling) |
| Downscale | LANCZOS resize to 1080×1350 |
| Format | PNG (optimised) |
| Slides per pick | 3 |

### Two visual themes

**Betslip Night** (default — everyday picks)

| Element | Value |
|---------|-------|
| Background | `#0B0F0D` (Ink Black) |
| Surface/card | `#111815` |
| Text | `#EAF7EF` (Paper White) |
| Muted | `#6B7A72` |
| Accent | Rotates: green/blue/amber/pink (see above) |
| Grid overlay | Subtle 60×60 dot grid |

**Matchday Print** (big games, finals, World Cup knockouts)

| Element | Value |
|---------|-------|
| Background | `#F4EEE2` (Cream) |
| Ink | `#16130F` |
| Accent | `#E8402A` (Red) + `#FFD400` (Yellow) |

### Fonts

All fonts must exist in `fonts/` directory (auto-downloaded by generate.yml at runtime):

| Font | File | Used for |
|------|------|---------|
| Archivo Black | `Archivo-Black.ttf` | Cover headlines, wordmark |
| Space Grotesk Bold | `SpaceGrotesk-Bold.ttf` | Match names, selection |
| Space Grotesk Medium | `SpaceGrotesk-Medium.ttf` | Body text, analysis |
| Space Mono Bold | `SpaceMono-Bold.ttf` | Odds, labels, tags |
| Space Mono Regular | `SpaceMono-Regular.ttf` | Muted labels |
| Anton Regular | `Anton-Regular.ttf` | Matchday Print giant headlines |
| Barlow Condensed Bold | `BarlowCondensed-Bold.ttf` | Matchday Print kickers |

Fallback: DejaVu Sans → Liberation Sans → PIL default (graceful degradation if fonts unavailable).

### Slide structure

**Slide 1 — Cover**
- Sport tag (top, Space Mono)
- Cover theme (e.g. "VALUE ALERT", "BANKER OF THE DAY")
- Big headline — the pick selection
- Date top-right: format `MON 7 JUL`
- PuntMate logo (from `assets/logo.png`)
- "SWIPE →" CTA

**Slide 2 — The Tip**
- Betslip-style card
- MATCH / SELECTION / DECIMAL ODDS
- Tier indicator
- Odds disclaimer: *"Odds indicative only. Confirm with your betting provider."*

**Slide 3 — The Breakdown**
- 2–3 sentence analysis paragraph
- Confidence dots (1–5 filled circles)
- Risk tagline (STRONG VALUE / CLEAR EDGE / SOLID VALUE / GOOD VALUE)
- Follow CTA: "@puntmatenz"
- Responsible gambling footer: `R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz`

### Output naming convention

```
data/cards/YYYY-MM-DD_{MatchLabel}_{theme}_{slide#}_{type}.png
```

Examples:
```
2026-07-06_Storm_vs_Titans_night_1_cover.png
2026-07-06_Storm_vs_Titans_night_2_tip.png
2026-07-06_Storm_vs_Titans_night_3_breakdown.png
```

Themes: `night` (Betslip Night) or `print` (Matchday Print).

---

## 6. Platform Publishing Specs

### Telegram (@puntmatenz)

API: `https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto` and `/sendMessage`

**For image + caption posts (`sendPhoto`):**
```
chat_id: TELEGRAM_CHANNEL_ID
caption: (see format below)
parse_mode: Markdown
photo: binary file upload
```

**For text-only posts (`sendMessage`):**
```
chat_id: TELEGRAM_CHANNEL_ID
text: (message body)
parse_mode: Markdown
```

**Caption format (Telegram):**
```
*🎯 PUNTMATE NZ — {SPORT_LABEL}*

🏟 {Match}

*PICK:* {SELECTION}
*ODDS:* {odds} ({market})

_{analysis}_

Confidence: ●●●○○ MODERATE
Edge: +12%

──────────────────
📲 Join Telegram for daily picks
R18 · Gamble responsibly · 0800 654 655
```

Telegram supports `*bold*` and `_italic_` Markdown. Keep captions punchy — the card carries the detail.

**Responsible gambling line used in Telegram:** `_All analysis is for entertainment only. Bet responsibly — Problem Gambling Foundation NZ: 0800 664 262_`

### Facebook Page

Page ID: `1173598642506628`

API endpoint: `POST https://graph.facebook.com/v19.0/{PAGE_ID}/photos`

```python
data = {
    "url": catbox_image_url,   # publicly accessible image URL
    "caption": caption_text,   # plain text — no Markdown
    "access_token": META_PAGE_TOKEN,
}
```

Falls back to `/{PAGE_ID}/feed` (text only) if no image URL is available.

**Note:** Facebook captions don't support Markdown — strip `*` and `_` characters. Slightly longer than Telegram is fine (3–4 lines).

**Token:** `META_PAGE_TOKEN` in GitHub Secrets. Short-lived (~60 days). To refresh:
1. Go to [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/)
2. Select PuntMate NZ app
3. Set User or Page to: PuntMate NZ
4. Copy the page access token → update the `META_PAGE_TOKEN` GitHub Secret

For a long-lived (non-expiring) token:
```
GET /oauth/access_token
  ?grant_type=fb_exchange_token
  &client_id={META_APP_ID}
  &client_secret={META_APP_SECRET}
  &fb_exchange_token={short_lived_token}
```

Meta App ID: `1032743613026672`

### Instagram

**Status: ✅ Active.** `IG_USER_ID` = `17841415246709818` (confirmed July 2026)

Instagram Business account (`@puntmatenz`) is linked to the PuntMate NZ Facebook Page. The `META_PAGE_TOKEN` secret holds a Page Access Token with `instagram_content_publish` and `instagram_basic` permissions — required for posting.

**To re-setup from scratch (if ever needed):**
1. On Instagram mobile: Settings → Account → Switch to Professional Account → Business
2. Link to the PuntMate NZ Facebook Page when prompted
3. In Graph API Explorer (with PuntMate NZ Page Token): `GET /1173598642506628?fields=instagram_business_account`
4. Copy the returned `id` → set as `IG_USER_ID` GitHub Secret
5. Ensure `META_PAGE_TOKEN` includes `instagram_basic` and `instagram_content_publish` permissions

**Once set up, posting flow (Meta Content Publishing API):**
1. `POST /{IG_USER_ID}/media` with `image_url` and `caption` → returns `container_id`
2. Wait 5 seconds (Meta processes the image)
3. `POST /{IG_USER_ID}/media_publish` with `creation_id: container_id` → post goes live

---

## 7. GitHub Secrets Reference

Set at: repo → Settings → Secrets and variables → Actions → Repository secrets

| Secret | Description | Notes |
|--------|-------------|-------|
| `ANTHROPIC_API_KEY` | Claude API key | platform.anthropic.com — ~$0.10/month |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Create via @BotFather |
| `TELEGRAM_CHANNEL_ID` | Channel ID (negative number) | e.g. `-1001234567890` |
| `ODDS_API_KEY` | The Odds API key | the-odds-api.com — free tier, 500 req/month |
| `META_PAGE_TOKEN` | Facebook/Instagram Page access token | Expires ~60 days — see refresh above |
| `FB_PAGE_ID` | Facebook Page ID | `1173598642506628` |
| `IG_USER_ID` | Instagram Business account user ID | `17841415246709818` — confirmed July 2026 |
| `FACEBOOK_PAGE_TOKEN` | (legacy — same as META_PAGE_TOKEN) | Used by daily_picks.yml |
| `FACEBOOK_PAGE_ID` | (legacy — same as FB_PAGE_ID) | Used by daily_picks.yml |
| `INSTAGRAM_ACCESS_TOKEN` | (legacy) | Same value as META_PAGE_TOKEN |
| `IMGUR_CLIENT_ID` | Imgur API client ID | Was used for image hosting; replaced by catbox.moe in current pipeline |

---

## 8. GitHub Actions Workflows

### `generate.yml` — PuntMate Social: Generate & Approve (ACTIVE)

The main production workflow.

**Triggers:**
- `cron: '0 20 * * *'` — 8am NZT daily
- `cron: '0 6 * * 5,6,0'` — 6pm NZT Fri/Sat/Sun
- `workflow_dispatch` — manual trigger

**Jobs:** `generate` → `approve` (environment gate)

**What it does:** Runs full picks pipeline (Telegram only), logs picks, uploads card to catbox.moe, saves `data/social_post.json`, commits to main, then waits for Micah to approve in the GitHub Actions UI before triggering publish.yml.

### `publish.yml` — PuntMate Social: Publish (ACTIVE)

**Triggers:**
- `workflow_run` from `generate.yml` on completion (success only)
- `workflow_dispatch` — manual trigger for retries

**What it does:** Reads `data/social_post.json`, posts to Instagram (if configured) and Facebook.

### `check_results.yml` — PuntMate Check Results (ACTIVE)

**Triggers:**
- `cron: '0 11 * * *'` — 11pm NZT daily

**What it does:** Resolves pending picks against completed scores, posts results to Telegram, commits updated `data/picks.json`.

### `daily_picks.yml` — PuntMate Daily Picks (DISABLED / LEGACY)

**Cron triggers are commented out.** Only triggerable via `workflow_dispatch` for testing. Superseded by `generate.yml`. Do not re-enable the cron — it will cause duplicate Telegram posts.

---

## 9. Manual Posting (Ad-hoc)

For one-off posts (specific round, big game, ad-hoc) outside the automated pipeline.

### Option A: Edit and run post_r19.py

`scripts/post_r19.py` is a standalone script — reads `.env` directly, doesn't need GitHub Actions. Edit the hardcoded card paths and caption strings, then run locally:

```bash
cd /Users/reina/Desktop/puntmate
python3 scripts/post_r19.py
```

### Option B: Double-click `post_r19_now.command`

Shell script at the repo root. Runs `post_r19.py`, then `git add . && git commit && git push`. Double-click from Finder to execute.

### Option C: Trigger workflow_dispatch manually

GitHub → Actions → "PuntMate Social — Generate & Approve" → Run workflow. Useful for running the full automated pipeline on demand outside the cron schedule.

### Generating cards locally

```bash
cd /Users/reina/Desktop/puntmate
python3 scripts/generate_picks_image.py
```

Cards are saved to `data/cards/`. Fonts must be present in `fonts/` — run `download_fonts.sh` first if needed.

---

## 10. Results Tracking

### Picks ledger (`data/picks.json`)

Every pick is logged with a unique ID, result, and P&L. Structure:

```json
{
  "id": "2026-07-06_rugbyleague_nrl_Melbourne_Storm_punter",
  "date": "2026-07-06",
  "personality": "punter",
  "sport_key": "rugbyleague_nrl",
  "sport": "NRL",
  "match": "Melbourne Storm vs Gold Coast Titans",
  "home_team": "Melbourne Storm",
  "away_team": "Gold Coast Titans",
  "pick": "MELBOURNE STORM",
  "market": "Head to Head",
  "odds": 1.40,
  "confidence": "High",
  "result": "win",
  "pnl": 4.00
}
```

Results are resolved by `check_results.py` running nightly at 11pm NZT.

**Flat stake:** $10 NZD per pick (for P&L calculation).

### Results Telegram posts

`post_results_telegram.py` formats a per-personality breakdown:

```
📊 Investor: 5W 2L | +$34
🎯 Punter: 3W 4L | -$13
🎰 Gambler: 1W 3L | -$17

Recent: Storm WIN ✅ · Warriors LOSS ❌ · ...
```

### Weekly P&L posts (planned)

The data is all there in `picks.json` — a weekly summary post isn't yet automated but can be generated from the ledger any time:

```python
import json
picks = json.load(open('data/picks.json'))
settled = [p for p in picks if p['result'] in ('win', 'loss')]
total_pnl = sum(p['pnl'] for p in settled)
wins = sum(1 for p in settled if p['result'] == 'win')
```

---

## 11. How to Tweak Things

### Change card design (colours, fonts, layout)

Edit: `scripts/generate_picks_image.py`

Key areas:
- **Betslip Night palette:** `NIGHT` dict and `NIGHT_ACCENTS` dict near top of file
- **Matchday Print palette:** `PRINT` dict
- **Font sizes:** `_f('Archivo-Black.ttf', SIZE)` calls throughout draw functions
- **Slide layout:** each slide has its own function (`_draw_cover_night`, `_draw_tip`, etc.)
- **Accent rotation order:** `ACCENT_SEQUENCE` list in `generate_pick.py`

### Change posting copy / caption format

**Telegram captions:** `_format_telegram_pick()` in `scripts/main.py`

**Facebook captions:** `post_personality_block()` in `scripts/post_facebook.py` or the caption builder in `generate.yml`'s `Build caption & save social_post.json` step

**Responsible gambling line:** Search for `RESPONSIBLE_LINE` in `post_telegram.py` and `post_facebook.py`

### Change pick criteria / value threshold

Edit: `scripts/generate_pick.py`

- **Minimum edge:** `MIN_EDGE_PCT = 7.0` — raise this to be more selective
- **System prompt:** `SYSTEM_PROMPT` string — adjust tone, sports focus, analysis framework
- **Value prompt structure:** `_build_value_prompt()` — change how matches are presented to the model
- **Confidence thresholds:** `edge_to_confidence()` function

### Change which sports are covered

Edit: `scripts/fetch_odds.py`

- **Sports list:** `SPORTS` list — add/remove Odds API sport keys
- **Sport labels:** `SPORT_LABELS` dict — human-readable names for cards
- **Big game detection:** `BIG_GAME_SPORTS` set and `BIG_GAME_KEYWORDS` list

### Change the posting schedule

Edit: `.github/workflows/generate.yml`

```yaml
on:
  schedule:
    - cron: '0 20 * * *'   # 8am NZT daily
    - cron: '0 6 * * 5,6,0' # 6pm NZT Fri/Sat/Sun
```

NZT = UTC+12. To convert: NZT time → subtract 12 hours → UTC cron time.

### Add Instagram posting (complete setup)

1. Complete Instagram linking (see Section 6 — Instagram setup steps)
2. Set `IG_USER_ID` and ensure `META_PAGE_TOKEN` is current in GitHub Secrets
3. `publish.yml` already has the full Instagram posting code — it just skips if `IG_USER_ID` is empty

### Add a new platform

1. Create `scripts/post_{platform}.py` following the pattern of `post_telegram.py`
2. Add credentials as GitHub Secrets
3. Add a new step in `publish.yml` (for image platforms) or in `main.py` (for text-first platforms)
4. Add the secret names to `daily_picks.yml` if re-enabling that workflow

### Change the image hosting service

Currently uses **catbox.moe** (free, anonymous, no API key needed). If it becomes unreliable:

Edit the "Upload picks card" step in `generate.yml`. The output must be a publicly accessible `https://` URL that Meta's servers can fetch. Alternatives: Imgur (needs `IMGUR_CLIENT_ID`), Cloudinary, or any public CDN.

### Refresh the Facebook/Instagram token

Tokens expire ~60 days. When posting fails with a token error:

1. Graph API Explorer → PuntMate NZ app → Get Page Access Token for PuntMate NZ page
2. Update `META_PAGE_TOKEN` secret in GitHub (and `FACEBOOK_PAGE_TOKEN` if still used)
3. Optionally exchange for a long-lived token (see Section 6)

---

## 12. Costs & API Usage

| Service | Usage | Cost |
|---------|-------|------|
| Anthropic (Claude Sonnet 4.6) | 1 API call/day for pick analysis | ~$0.10–0.30/month |
| The Odds API | ~2–3 requests/day (~60–90/month) | Free (500 req/month limit) |
| Telegram Bot API | Unlimited | Free |
| Facebook Graph API | Standard usage | Free |
| catbox.moe (image hosting) | 1 upload/day | Free |
| GitHub Actions | ~15 min/day across 3 workflows | Free (within free tier) |

**No AI tokens used for:** card generation (Pillow), posting (API calls), results checking (score lookups).

**To reduce token usage:**
- `MIN_EDGE_PCT` already filters out low-confidence picks early, before the model call
- The model is called once per run with all matches batched in a single prompt — not per-match
- Keep the `SYSTEM_PROMPT` and `_build_value_prompt()` lean

---

## 13. Roadmap / Planned Features

**Instagram (done ✅ July 2026):**
- Business account linked, IG_USER_ID and META_PAGE_TOKEN both set with `instagram_content_publish` permission
- `publish.yml` code already handles the 2-step container create → publish flow
- Stories format (1080×1920) still needs a separate card template function in `generate_picks_image.py`

**Instagram Stories:**
- Different aspect ratio: 9:16 (1080×1920)
- More casual tone, "swipe up" CTA
- Needs a `_draw_story_*` set of functions added to `generate_picks_image.py`

**Weekly P&L summary post:**
- Auto-generate every Monday from `data/picks.json`
- Format: "This week: 4W 2L | Investor +$32 | Punter -$10"
- Add a new `post_weekly_summary.py` and a `weekly_summary.yml` workflow (cron: Monday morning NZT)

**Multi picks:**
- `data/cards/` already has multi-card naming convention in place
- Needs a multi-leg card template in `generate_picks_image.py` (Slide 2 shows legs list + combined odds)
- Logic in `generate_pick.py` to detect when 2+ same-day picks form a strong multi

**Paid tier:**
- Current Telegram channel is free/public — paid sub channel is a future option
- Separate `@puntmatenz_pro` channel with more picks, deeper analysis
- Stripe + Telegram Stars or MemberSpace integration

---

*To run a manual post right now: double-click `post_r19_now.command` or trigger `workflow_dispatch` from the GitHub Actions tab.*
