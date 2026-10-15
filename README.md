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
   GitHub Actions UI. Only runs if **generate** itself fully succeeded
   (`needs.generate.result == 'success'`) — see Reliability below.
3. **on_reject** *(only if rejected/cancelled)* — records `REJECTED`, sends a
   rejection email, nothing is published.
4. **publish** *(only if approved)* — re-verifies every file's SHA-256
   checksum against `manifest.json` (refuses to publish on any mismatch),
   then posts to Telegram and Instagram independently — one platform failing
   never blocks or undoes another's success — and emails the result. A
   mixed outcome is recorded and emailed as `PARTIALLY_PUBLISHED`, never
   silently reported as a plain success; `publish.yml` (Manual Republish)
   can then resend only the platforms that didn't succeed the first time,
   without re-posting to ones that already did.

### No-bet days: Watchlist + Degen Watch

On a genuine no-bet day (no candidate clears the value bar), two
independent, explicitly-unofficial things get posted instead of the real
pick — automatically, no approval step, same as the real daily pick's
trial flow:

- **Watchlist** (Telegram only) — today's most notable fixtures, no
  selections, no odds, nothing framed as advice.
- **Degen Watch** (Telegram + Instagram) — the candidate closest to
  clearing the 7% value bar but which still fell short
  (`generate_pick.select_closest_to_passing`, over the same
  `rejected_candidates` the run already produces — never a second
  ledger or a loosened gate). Always labelled "UNOFFICIAL — didn't clear
  our bar" and "not a PuntMate pick", and always validated through the
  strictest responsible-gambling language check regardless of the
  candidate's real risk tier. Never counted toward the public strike
  rate, RECAP.md, or any ledger — it's content, not a tracked pick.
  Instagram is skipped (not failed) if the card doesn't render; one
  platform failing never blocks the other, same guarantee as the real
  pick.

### Reliability

- Every run writes `data/latest_run.json` exactly once, through a single
  function, on every exit path — including empty fixtures and Odds API
  failures, which previously wrote nothing at all and left a stale prior
  day's file in place for the next step to misread as fresh. Each write
  carries a never-reused `run_id` and one of seven statuses
  (`scripts/run_status.py`) that separate an honest no-value day
  (`NO_VALUE`, `INSUFFICIENT_EVIDENCE`) from an operational failure
  (`BAD_ODDS`, `MODEL_ERROR`, `ODDS_API_ERROR`, `RENDER_ERROR`) —
  `PICK_READY` is the only status that means a real pick was selected.
- `build_review_package.py` refuses to build a review package when
  `latest_run.json`'s `run_id` doesn't match the current job's
  `GITHUB_RUN_ID` (generate and the review-package build always run in the
  same workflow run — see `generate.yml`'s module docstring) — a leftover
  file from a different run can never be silently frozen as today's pick.
- **approve**, **on_reject** and **publish** (and their weekend
  equivalents) all require `needs.generate.result == 'success'` before
  acting on generate's outputs. A job's outputs stay set to whatever an
  earlier successful step produced even if a later step in that same job
  fails (e.g. a git push hitting a real rebase conflict) — without this
  check, publish could still try to download a review artifact that was
  never uploaded.

### Proposed, not live: conservative mode

`scripts/conservative_mode.py` is a second, independent ranking over the
exact same candidates `generate_pick.py` already finds (nothing bypasses
or loosens the existing value/evidence gate) — picks the highest estimated
win probability among `confidence == "HIGH"` candidates, with no odds
ceiling or floor, so a short price is never treated as "safe" just for
being short. It's fully tested but **not wired into `main.py`'s live run**
— its one open parameter, `CONSERVATIVE_MIN_PROBABILITY`, is a proposed
default pending Micah's sign-off (see the module's docstring), and nothing
here publishes anywhere until that's settled.

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
  own fire time** (`fetch_odds.fetch_upcoming_odds(sport_keys, hours_ahead=24)`),
  not a fixed calendar day — so "today's" fixtures shift along with the
  daily cron's own UTC/NZT drift (see above), and the weekend multi widens
  this to ~76h to pool Fri/Sat/Sun together (`generate_weekend_multi.py`).
  2026-10-15: `sport_keys` is required — the daily run now queries only
  the <=2 sports `research_shortlist.py` shortlisted that day (an empty
  list costs zero credits), not the full registry; see
  `quota_budget.py` for why.
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
