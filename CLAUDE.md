# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

PuntMate NZ is **not a web app** — it's a scheduled Python pipeline (run entirely by
GitHub Actions cron) that picks one sports bet per day, renders branded image cards for
it, and posts the result to Telegram/Instagram/Facebook. There is no server, no
database, no frontend build. State lives in committed JSON files under `data/`, and the
git history of that directory *is* the audit trail.

Each run selects **one official pick** (or explicitly returns **NO_BET**), classifies it
on two independent axes — risk (`STANDARD_PICK` / `RISKY_PICK`) and bet type
(`INVESTOR_BET` / `PUNTER_BET` / `GAMBLER_BET` / `NO_BET`) — renders the brand-kit
cards, freezes everything with SHA-256 checksums, and (in the current trial config)
auto-publishes once the copy validator passes. `config/auto_publish` controls whether a
human approval gate is required instead — see "The two operating modes" below.

Read `OPERATIONS.md` first for current live status/switches, then `PUNTMATE_WORKFLOW.md`
for exhaustive detail (card specs, platform API notes, "how to tweak X" cookbook). This
file is the architecture map; those two are the operational reference.

## Commands

```bash
# Install
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # only needed for card rendering

# Run the full test suite (173 tests, no live API calls — everything is mocked)
python -m unittest discover -s tests
# or, per OPERATIONS.md convention:
pytest tests/

# Run a single test file / test case
python -m unittest tests.test_generate_pick
python -m unittest tests.test_generate_pick.SomeTestCase.test_something

# Run the picks pipeline locally (prepare stage only — never posts anywhere)
cd scripts && python main.py                 # needs ANTHROPIC_API_KEY, ODDS_API_KEY
cd scripts && python build_review_package.py # freeze the review package + checksums
cd scripts && python send_preview.py         # email the approval preview

# Render cards for a specific pick file, or run the renderer self-test fixtures
python scripts/render_brand_templates.py --pick-file data/latest_run.json --pick-index 0
python scripts/render_brand_templates.py --test-portugal-spain --out-dir data/cards/_selftest
python scripts/render_brand_templates.py --test-overflow --out-dir data/cards/_selftest

# Inject a synthetic test pick to exercise render -> freeze -> preview without live odds
cd scripts && python inject_test_pick.py && python render_latest_pick.py
```

GitHub Actions is the only environment secrets are actually available in (`ANTHROPIC_API_KEY`,
`ODDS_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`, `IG_USER_ID`, `META_PAGE_TOKEN`,
`FACEBOOK_PAGE_ID`, `GMAIL_SENDER_EMAIL`, `GMAIL_APP_PASSWORD`, `PUNTMATE_REPORT_EMAIL` — see
`.env.example`). Locally you can run the pipeline scripts with a `.env` for manual testing, but
CI never reads it — it injects secrets directly. Every workflow can also be triggered manually
(`workflow_dispatch`) with `dry_run: true` (default) to exercise the whole pipeline without
posting anywhere.

## Architecture: the pipeline, stage by stage

Everything downstream reads/writes `data/latest_run.json` and `data/review/<pick_id>/` —
there's no shared runtime state beyond these files. The four GitHub Actions workflows
(`.github/workflows/*.yml`) are the actual orchestrator; the Python scripts are stateless
steps chained through those files. `daily_picks.yml` no longer exists — `generate.yml`
replaced it.

1. **`main.py`** (the `generate` job) — fetches odds (`fetch_odds.py`, The Odds API),
   fetches + validates research (`fetch_news.py` → `research_validator.py`, which rejects
   cross-sport-contaminated snippets), and calls `generate_pick.py` to select one pick.
   Writes `data/latest_run.json`. Never posts anything, never emails.

2. **`generate_pick.py`** — asks Claude to propose every genuinely defensible
   match+market candidate (probability estimate, confidence, uncertainty flags — no
   verdict, no tone from the model). `pick_classifier.py` (pure Python, no LLM) then
   deterministically decides each candidate's risk tier and bet type from that evidence.
   If more than one candidate clears the bar, the featured pick is chosen by a fixed
   tie-break (Investor > Punter > Gambler, then Standard > Risky, then edge%) — never
   upgraded/invented to fill a quota. If nothing clears the bar, the result is `NO_BET`
   (day-level marker only — `classify()` itself never returns it as a pick classification).

3. **Rendering** — `render_brand_templates.py` drives a headless Chromium (Playwright)
   through the actual approved `brand/Templates/*.dc.html` React templates and
   screenshots them, so output is pixel-identical to the approved Brand Kit rather than a
   hand-redrawn approximation. `generate_picks_image.py` (Pillow) is a documented, still
   maintained fallback if Playwright rendering throws — `main.py`'s `render_card()` tries
   Playwright first, falls back automatically. There is no Pillow fallback for multi
   graphics (`render_multi`) — if that fails, the tier's Telegram text still posts, just
   without an Instagram graphic that run.

4. **`build_review_package.py`** (freeze stage) — takes the rendered pick and writes
   `data/review/<pick_id>/`: `telegram-post.txt`, `instagram-caption.txt`,
   `post-metadata.json`, `preview.html`, copies of the final PNGs, and `manifest.json`
   (SHA-256 + byte count of every file above, via `manifest.py`). Runs the drafted copy
   through `copy_validator.py` first — a **hard fail** here stops the whole job, nothing
   downstream ever runs. **Nothing written here may be regenerated afterward.**
   `pick_id` is `<date>_<slugified-match>`, with a `_dryrun` suffix for dry runs so manual
   test runs can never collide with, or terminally block, a same-day live pick_id (see
   the module docstring — this is the fix for a real incident, commit 7dcfbc7).

5. **`send_preview.py`** — transitions workflow state
   `GENERATED → PREVIEW_READY → AWAITING_APPROVAL` (`workflow_state.py`) and emails the
   Gmail approval preview (`email_service.py`).

6. **Approval gate** (`approve` job) — a GitHub Actions `environment: production` gate
   with a required reviewer. Skipped entirely when `config/auto_publish` is `true` (see
   below) — in that mode the copy validator from step 4 is the *only* gate.

7. **`publish_pick.py`** (the only script that ever calls the Telegram/Instagram/Facebook
   APIs) — downloads *this run's own* frozen artifact, re-hashes every file in
   `manifest.json` and refuses to publish anything on a single mismatch
   (`manifest.verify_manifest`), then posts to each platform **independently** — one
   platform failing never blocks or rolls back another's success. Records
   `data/published/<pick_id>.json` and the terminal workflow state
   (`PUBLISHED` / `PARTIALLY_PUBLISHED` / `PUBLISH_FAILED`).

8. **`check_results.py`** (separate `check_results.yml`, 11pm NZT) — resolves pending
   picks against final scores, updates `data/results/picks_ledger.json` and
   `config/challenge.json`, posts a results summary to Telegram
   (`post_results_telegram.py`).

9. **`weekly_recap.py`** (Sunday, `weekly_recap.yml`) — strike rate by bet type, appended
   permanently to `RECAP.md`.

The **weekend multi** path (`generate_weekend_multi.py` → `build_weekend_multi_package.py`,
Friday-only job set in `generate.yml`) is a completely separate pipeline that pools
Fri/Sat/Sun fixtures into Punter/Gambler-Degenerate multi legs. The regular daily
`generate` job never builds multis (`build_multis` defaults to `False`).

### Why the freeze/checksum/state-machine design exists

This isn't defensive boilerplate — every one of these mechanisms maps to a real incident
that happened in production (see `OPERATIONS.md` and commit messages referenced in the
docstrings):

- **`workflow_state.py`** enforces an explicit allow-list of forward transitions. The one
  transition that must be structurally impossible is `REJECTED → PUBLISHED`. `PUBLISHED`
  and `REJECTED` are terminal — nothing can follow them except the narrow, explicit
  "resend failed platforms" retry paths out of `PARTIALLY_PUBLISHED`/`PUBLISH_FAILED`.
- **`manifest.py`** freeze/checksum verification exists so `publish_pick.py` can never
  post something different from what was actually reviewed — no regeneration between
  approval and publish, enforced in code, not just policy.
- **`copy_validator.py`** exists because a real post once shipped with NO_BET-only
  reasoning text ("no pick meets my criteria... sitting this one out") sitting inside a
  post that still named a live pick and its odds — a contradiction between verdict and
  copy. It also bans staking/unit language (PuntMate never tells anyone how much to bet)
  and corporate/financial-analyst tone ("capital allocation", "portfolio", etc. — PuntMate
  talks like a mate who knows the sport).
- **`research_validator.py`** exists because the old news fallback appended a hardcoded
  sport-specific search term to every query, so a FIFA World Cup fixture could pull back
  NRL headlines that merely happened to share team names — contradictory research the
  model then reasoned from.
- **`main.py`'s `_already_actioned_today` / `_recently_actioned_slugs`** guard against two
  separate incidents: a same-day re-run independently reselecting a fixture that already
  has pipeline state today (would crash `workflow_state.transition` with
  `InvalidTransitionError`), and a fixture stuck in `PARTIALLY_PUBLISHED` repeatedly
  trapping every subsequent run into an all-day skip (fixed by excluding by *match slug*,
  not by pick_id).

If you're touching any of these four files, read the module docstring in full first — the
history is the spec.

### The two operating modes

`config/auto_publish` (a one-line file, `true`/`false`) is the single switch between:
- **`true`** (current trial, since 2026-07-18): scheduled runs skip the human approval
  gate entirely; `copy_validator.py`'s hard-fail is the only gate.
- **`false`**: the `approve` job (GitHub environment gate, required reviewer) blocks every
  publish until a human clicks Approve/Reject in the Actions UI.

`config/focus_matches.txt` lists keywords for fixtures to prioritise in tie-breaks (never
manufactures a pick, never dropped by the prompt cap). Both are meant to be edited +
committed directly — no code change needed for either.

## Key conventions

- **Read the module docstring before editing any script in `scripts/`.** Nearly every
  script's top-of-file comment records a specific production incident and why the current
  behaviour exists — skipping it risks reintroducing a bug that already shipped once.
  Same for inline comments dated `YYYY-MM-DD (Micah): ...` — those are decisions, not
  scaffolding to clean up.
- **Never let the freeze/checksum/state-machine gates be bypassed** "to make something
  post" — if a run is stuck, fix the root cause (see `OPERATIONS.md`'s known-limitations
  section) rather than hand-editing `data/state/*.json` or `data/published/*.json`.
- Tests mock every external API (Anthropic, The Odds API, Telegram, Meta Graph, Gmail) —
  no test should ever make a live network call. Follow that pattern for new tests.
- `data/` is committed, not gitignored — `data/review/**/*.png` needs to be publicly
  fetchable via `raw.githubusercontent.com` for Meta's Graph API to pull images from, and
  `data/state/`, `data/published/`, `data/picks.json` are the permanent pick history/audit
  trail. Don't treat `data/` as disposable build output.
- Card image filenames follow `data/cards/YYYY-MM-DD_<match>_<theme>_<n>_<slide>.png`
  (e.g. `_1_cover`, `_2_tip`, `_3_breakdown`, plus a separate `_story.png`) — see
  `render_brand_templates.py`'s docstring for the exact convention.
- `pick_id` format is `<run_date>_<slugified match>`, with a `_dryrun` suffix for
  non-live runs and `_no-bet` / `_weekend_multi` for those special cases — always derived
  via the shared helpers (`render_brand_templates.slugify`,
  `build_review_package._pick_id_suffix`), never hand-built inline.
- `legacy/` is round-specific one-off scripts kept for reference only — not part of the
  maintained pipeline; don't build on it.
- Brand/design work (colours, fonts, card layout) lives in `brand/Templates/*.dc.html` —
  these are the source of truth the renderer screenshots; read `brand/README.md`'s "never
  post the same format twice" rotation rule before changing defaults.
