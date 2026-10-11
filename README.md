# PuntMate NZ 🎯

Automated sports picks for NZ audiences — NRL, FIFA World Cup, Super Rugby,
UFC/MMA, Wimbledon.

Each run selects **one official pick** (or explicitly returns **NO_BET** when
nothing clears the bar), classifies it on two independent axes — risk
(`STANDARD_PICK` / `RISKY_PICK` / `NO_BET`) and bet type (`INVESTOR_BET` /
`PUNTER_BET` / `GAMBLER_BET` / `NO_BET`) — renders the brand-kit cards,
freezes everything with SHA-256 checksums, emails Micah a preview, and waits
for manual approval in GitHub Actions before posting anything to Telegram or
Instagram. Facebook is never posted to directly (see "Facebook" below).

## Setup

### 1. Get API keys / secrets

| Secret | Where | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | platform.anthropic.com | pick generation |
| `ODDS_API_KEY` | the-odds-api.com | free tier, ~2-3 req/day |
| `TELEGRAM_BOT_TOKEN` | @BotFather on Telegram | |
| `TELEGRAM_CHANNEL_ID` | see below | |
| `IG_USER_ID` | Meta Graph API | Instagram feed + Story posting |
| `META_PAGE_TOKEN` | Meta Graph API | Page access token linked to the IG account |
| `GMAIL_SENDER_EMAIL` | your Gmail address | account PuntMate emails FROM |
| `GMAIL_APP_PASSWORD` | Google Account → Security → App Passwords | **not** your normal Gmail password |
| `PUNTMATE_REPORT_EMAIL` | your address | where preview/result emails are sent TO |

Full names/notes also live in `.env.example`. Facebook's `FB_PAGE_ID` secret
is no longer required for posting (see below) but is harmless to leave set.

### 2. Get your Telegram Channel ID

1. Add your bot as admin to your channel
2. Send a test message to the channel
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the `chat.id` value — it will be negative (e.g. `-1001234567890`)

### 3. Add secrets to GitHub

Repo → Settings → Secrets and variables → Actions → New repository secret.
Add every key from the table above.

### 4. Set up the approval gate

Repo → Settings → Environments → **production** → Required reviewers → add
your GitHub username. This is the single approval gate that Telegram,
Instagram AND Facebook (via Instagram) all wait behind — nothing posts
anywhere until you click Approve on the `approve` job for a run.

If you reject a run instead, it's recorded as a terminal `REJECTED` state
(`data/state/<pick_id>.json`) and a rejection email is sent — that pick_id
can never be published later, by any retry.

### 5. Enable GitHub Actions

Push this repo to GitHub. The schedule runs automatically. To test manually:
Actions tab → "PuntMate Social — Generate & Approve" → Run workflow → leave
`dry_run: true` (default) to see the full pipeline without posting anything.

## How a run works

1. **generate** — fetch odds, fetch + validate research (rejects
   irrelevant-sport contamination — see `scripts/research_validator.py`),
   select one pick (or NO_BET), render cards, freeze the review package to
   `data/review/<pick_id>/` (`telegram-post.txt`, `instagram-caption.txt`,
   `post-metadata.json`, `manifest.json`, `preview.html`, PNGs), email the
   approval request.
2. **approve** — you review the email (or the job summary / `preview.html`
   artifact if email isn't configured) and click Approve or Reject in the
   GitHub Actions UI.
3. **on_reject** *(only if rejected/cancelled)* — records `REJECTED`, sends a
   rejection email, nothing is published.
4. **publish** *(only if approved)* — re-verifies every file's SHA-256
   checksum against `manifest.json` (refuses to publish on any mismatch),
   then posts to Telegram and Instagram independently — one platform failing
   never blocks or undoes another's success — and emails the result.

### Facebook

Direct Facebook Page posting is disabled — Meta deprecated the
`publish_actions` permission our Page token relied on (confirmed by a real
failed live post on 2026-07-14). Since the Facebook Page is already linked to
the Instagram account, Facebook is reported as **"expected via linked
Instagram account"** rather than claimed as a verified success.

## Schedule

- Daily main run: fires at a fixed 20:00 UTC. GitHub Actions cron is
  always UTC and can't express a time zone, so this is 8am NZT in NZST
  (roughly Apr-Sep) but 9am NZT in NZDT (roughly Sep-Apr) — a real hour of
  drift across each DST changeover, not just a rounding note. The
  pipeline's own "today" doesn't depend on which of those two hours it
  actually fires at: `run_date` and same-day dedupe are computed from the
  real Pacific/Auckland calendar date (`scripts/nz_date.py`), not from
  this cron time, so the drift can't produce a wrong business date or a
  duplicate/skipped day — it can still shift the actual posting time by
  an hour twice a year, which is a separate, not-yet-made schedule change.
- Weekend Punter/Gambler-Degenerate multi: fires 7am NZT Friday/Saturday/
  Sunday (moved 2026-07-19 from the original 6pm slot — too close to
  kickoff and outside NZ's actual morning engagement peak), same fixed-UTC
  DST caveat as above.

### Fixture window & prompt cap

- Each run fetches odds across a **rolling 24-hour window from the run's
  own fire time** (`fetch_odds.fetch_upcoming_odds(hours_ahead=24)`), not
  a fixed calendar day — so "today's" fixtures shift along with the daily
  cron's own UTC/NZT drift (see above), and the weekend multi widens this
  to ~76h to pool Fri/Sat/Sun together (`generate_weekend_multi.py`).
- If more than 25 fixtures come back in that window, only the first 25 are
  put in front of the model (`generate_pick.MAX_MATCHES_IN_PROMPT`) —
  owner-focus fixtures first, then sport priority — and the run's
  `research_warnings` records exactly how many fixtures were available and
  how many were dropped, so a quiet slate and a capped one never look the
  same in the review email.
- A sport (e.g. UFC/MMA, international Test rugby) having zero fixtures on
  a given day is expected, not an error — most sports don't run daily.
  `fetch_odds.LAST_FETCH_ERRORS` distinguishes that from an actual Odds
  API failure for that sport (dead key, rate limit, timeout) — see
  `scripts/run_status.py`'s `ODDS_API_ERROR` status, which only fires on
  the latter.

## Tests

```
python -m unittest discover -s tests
```

Covers risk/bet-type classification, copy-consistency + tone + responsible-
gambling validation, research relevance validation, the freeze/manifest
system, and the full publish flow (success, partial failure, checksum
mismatch, rejection) — all against mocks, no live API calls.

## Stack

- **Odds**: The Odds API (free tier)
- **Research**: ESPN API + Google News RSS, filtered by `research_validator.py`
- **Picks**: Claude (Anthropic API) for evidence gathering; risk/bet-type
  classification is deterministic Python, not the model's own opinion
- **Rendering**: Playwright driving the actual approved Brand Kit `.dc.html`
  templates (Pillow kept as a documented fallback)
- **Posting**: Telegram Bot API, Meta Graph API (Instagram)
- **Email**: Gmail SMTP (`scripts/email_service.py`)
- **Runner**: GitHub Actions (free), environment-protected approval gate
