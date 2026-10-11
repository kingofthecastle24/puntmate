# PuntMate NZ — Operations Guide (for Micah + future Claude sessions)

_Last updated: 2026-07-18. If you're a Claude session picking this repo up
fresh: read this file first, then PUNTMATE_WORKFLOW.md for detail._

## What runs automatically
| When (NZT) | What | Workflow |
|---|---|---|
| 8am daily + 6pm Fri–Sun | Generate pick → validate → freeze → publish (Telegram, IG feed+story, FB via IG) | generate.yml |
| 11pm daily | Resolve results against scores | check_results.yml |
| 6pm Sunday | Weekly recap: strike rate by bet type → Telegram + RECAP.md | weekly_recap.yml |

## The switches (edit + commit, or ask Claude)
- `config/auto_publish` — `true` = no human approval gate (TRIAL mode, active
  since 2026-07-18). Flip to `false` to restore the gate. One line.
- `config/focus_matches.txt` — keywords for fixtures you want prioritised
  (e.g. `All Blacks`). Focus fixtures: never dropped by the prompt cap,
  flagged to the model, and win featured-pick ties among candidates that
  already cleared the bar. Focus never manufactures a pick.

## Hard guarantees (do not weaken)
- NO_BET floor: no genuine edge = no pick. Wider coverage + Watchlist posts
  exist so this stays rare without ever being faked.
- Copy validator hard-fails the run on internal/debug language, staking
  language, tone violations, contradiction — this is the only gate in
  auto-publish mode. See incident 2026-07-17 in commit 40e5ab7.
- Freeze/checksums: publish only ever sends the exact reviewed bytes.
- State machine: REJECTED/PUBLISHED are terminal; re-runs can't double-post.
- Multi fires only when 3+ candidates independently clear the bar on
  distinct matches. Never forced.

## Content formats
Daily pick (cards + caption, all platforms) · Watchlist on no-bet days
(Telegram text) · Rare multi (Telegram text, Gambler-tier, disclaimed) ·
Weekly recap (Telegram text + RECAP.md). Cards show game date via the sport
chip + kickoff line.

## Facebook (2026-07-19)
Direct Page posting is live in publish_pick.py via post_facebook.py — the
old "linked Instagram auto-shares" assumption was wrong (Meta never
cross-posts API-published IG content). Needs the FACEBOOK_PAGE_ID GitHub
secret (+ optionally FACEBOOK_PAGE_TOKEN — a PAGE token with
pages_manage_posts; falls back to META_PAGE_TOKEN). Until the secret is
added, Facebook reports "skipped" in run logs — not failed. Feed photo +
Page Story for the daily pick, feed photo per weekend-multi tier.

## The $100 -> $1,000 Challenge (built 2026-07-19, OFF by default)
Public notional challenge following the posted daily picks — 10% of the
challenge balance per settled pick, updated nightly by challenge_tracker.py
in check_results.yml, surfaced in the Sunday recap. Start it by setting
"enabled": true in config/challenge.json (start date stamps itself). Bust
and completion both stay on the record. Ledger: data/challenge.json.

## Owner private DM + personal bet log (added 2026-10-11)
A private Telegram DM to Micah for every official pick and weekend multi
that actually publishes — he follows every one of them, at his own flat
stakes, so there's no personal filtering and no separate picks. Entirely
separate from the public posts/ledger/copy validator, which are untouched.
- `scripts/owner_dm.py` — builds the DM from the exact frozen
  `data/review/<pick_id>/post-metadata.json` the public post was built
  from (never regenerated), appends a month-to-date staked/returned/net
  summary from `my_bets.py`, and sends it. Wired as its own step in
  `generate.yml`, right after the public publish step, in both the daily
  and weekend-multi jobs — gated on `has_pick`/`has_{tier}_multi` so it
  never fires on a No-Bet/Watchlist day. A DM failure is logged and can
  never affect the public publish outcome.
- Secret needed: `OWNER_CHAT_ID` (Micah's own Telegram chat id — reuses
  `TELEGRAM_BOT_TOKEN`). Missing secret = DM skipped, nothing else affected.
- `config/my_bets.json` — `single_stake` (2.00), `multi_stake` (5.00),
  `monthly_budget` (100), `tab_balance` (optional, Micah enters it by hand).
  Staking language is fine in the DM only — never public copy.
- `data/my_bets.json` — Micah's own log of bets he actually placed (not
  every published pick is necessarily logged — he adds one by hand after
  placing it himself on TAB):
  `python scripts/my_bets.py add <pick_id> [--tier punter|gambler|degenerate]`
- Resolution is automatic, nightly, in `check_results.yml` right after
  `check_results.py` — `python scripts/my_bets.py resolve`. Singles AND
  multi legs are resolved against real scores via the exact same market
  rules the public ledger uses (`check_results.resolve_market_result`,
  extracted so both share one source of truth). A multi needs every leg to
  win (a push leg doesn't block it). Results live ONLY in
  `data/my_bets.json` — never written into the public `data/picks.json`.
- `python scripts/my_bets.py summary [--month YYYY-MM]` — staked / returned
  / net / budget warnings, plus the public record's own P&L rescaled to
  Micah's stake for comparison. Budget warnings are warnings only — nothing
  is ever skipped or hidden.
- Nothing here touches TAB or any bookmaker — Micah places every bet by
  hand (Claude in Chrome on his Mac), always tapping Place Bet himself.

## Known limitations / watch items
- Auto-publish trial is NEW: first unsupervised scheduled run needs a glance.
- Watchlist + multi are unit-tested but haven't fired live yet.
- `rugbyunion_international` sport key unverified against The Odds API —
  check a run log's per-sport lines; harmless if invalid, but if it errors,
  ask Claude to find the right key for test rugby.
- Live posts from 2026-07-17 incident still contain leaked text (Micah to
  clean up manually if desired).
- The Odds API is the data source (AU-region books ≈ TAB NZ slate). No
  margin-band markets; handicap is the closest covered equivalent.

## Managing this with Claude
Start a Cowork session with this repo's parent folder connected. Say e.g.
"read OPERATIONS.md in the puntmate repo, then <task>". Push access works
via the git remote already configured in CI; local sessions clone with the
same token. Keep changes small, always run `pytest tests/` (104 tests), and
never bypass the validator/state machine to "make something post".
