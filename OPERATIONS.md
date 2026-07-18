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
