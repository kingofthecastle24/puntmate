# PuntMate NZ — Picks Recap

*As of 13 July 2026. Generated from `data/results/picks_ledger.json` — re-run `python3 scripts/recap_report.py --markdown` any time to refresh these numbers as new picks settle.*

## Headline numbers

| Tier | W | L | Win % | P&L ($10 units) |
|------|---|---|-------|------------------|
| 🏦 Investor | 2 | 0 | 100% | +$8.00 |
| 🎯 Punter | 1 | 0 | 100% | +$3.80 |
| 🎰 Gambler | 0 | 0 | — | no settled picks yet |
| **Overall** | **3** | **0** | **100%** | **+$11.80** |

**Multi (parlay), tracked separately from tier win %:** 0W 1L, -$10.00

## The picks

| Date | Tier | Match | Selection | Odds | Result |
|------|------|-------|-----------|------|--------|
| 6 Jul 2026 | Investor | Melbourne Storm vs Gold Coast Titans (NRL R19) | Storm to Win | 1.40 | ✅ WIN — Storm 22-18 |
| 7 Jul 2026 | Investor | Argentina vs Egypt (FIFA World Cup 2026, Round of 16) | Argentina to Win | 1.40 | ✅ WIN — Argentina 3-2 |
| 12 Jul 2026 | Punter | McGregor vs Holloway 2 (UFC 329) | Max Holloway to Win | 1.38 | ✅ WIN — Holloway TKO R1 |
| 6 Jul 2026 | Multi | Storm / Warriors (Tigers vs Warriors) / Dolphins (vs Sharks) — NRL R19 home treble | 3-leg multi | $2.98 | ❌ LOSS — Dolphins lost 12-24 to Sharks |

## Standouts

**Holloway TKOs McGregor in round 1.** The Punter-tier headline result — McGregor hurt his knee throwing a jumping kick to start the fight and Holloway finished it inside the first round. Clean win at 1.38.

**Argentina's stoppage-time comeback.** Egypt led 2-0 before Argentina scored three unanswered — Romero, Messi, then an Enzo Fernandez winner in stoppage time to seal it 3-2. A nervy one for an Investor-tier "safe" pick, but it landed.

**The multi was the only blemish.** Storm and Warriors both delivered, but the Dolphins fell to the Sharks (12-24), which sinks the whole 3-leg treble regardless of the other two legs winning. Straight moral: multis carry parlay risk even when 2/3 picks are right — worth flagging to followers if you post multis again.

## Data quality note — please read

Building this recap surfaced a few things worth fixing in the pipeline:

1. **`data/picks.json` (the "permanent ledger" per the workflow doc) is empty** — `[]`. The actual automated pipeline (`main.py` → `log_picks.py` → `data/picks.json`) doesn't appear to have ever run for real; there's no git history in the repo either (`git log` returns no commits). Everything recapped above was reconstructed from `data/results/picks_ledger.json`, `scripts/post_r19.py` (the confirmed real Telegram post), and the rendered card images in `data/cards/`, cross-checked against real match results.
2. **`data/results/picks_ledger.json` only had 1 of the 4 real picks logged** (Storm, still marked PENDING). I've added the other 3 and marked all 4 as settled — see the updated file.
3. **I found and excluded one likely test/demo pick: "Warriors vs Panthers" @ 2.40.** There's no real NRL fixture between Warriors and Panthers on or near 6 July 2026 (their real 2026 meetings are Round 13, 31 May, and Round 23, 7 Aug) — and the exact same "Warriors to Win 2.40" line shows up in a `data/cards/2026-07-06_results_2_card.png` mockup alongside three fully fictional bets (Broncos, Raiders/Roosters, Eels) that don't exist anywhere else in the data. That card set looks like template-testing content, not a real placed pick, so it's left out of the win % above. Worth a quick look to confirm and clean up those files if they're not needed.
4. **Going forward:** every time a pick settles, run `python3 scripts/update_result.py <pick_id> WIN|LOSS|VOID` (existing script) to update the ledger, then `python3 scripts/recap_report.py --markdown` to regenerate this recap's numbers. No new tooling to learn — just wire the ledger updates in as picks settle and this file stays current.


## Week 2026-07-11 → 2026-07-17 (auto-generated)

```
*📈 PUNTMATE NZ — WEEKLY RECAP*
_11 Jul – 17 Jul 2026_

*Overall: 1W – 3L  ·  Strike rate 25%*

📊 Investor: 0W – 0L  (—)
🎯 Punter: 0W – 0L  (—)
🎰 Gambler: 0W – 1L  (0%)
📁 Pre-rebuild picks: 1W – 2L (counted in overall)

⏳ 4 pick(s) still to settle — counted next week, never guessed.

Every result on the record, wins and losses alike.

──────────────────
📲 Join Telegram for daily picks
R18 · Gamble responsibly · Problem Gambling Foundation NZ: 0800 664 262
```


## Week 2026-07-13 → 2026-07-19 (auto-generated)

```
*📈 PUNTMATE NZ — WEEKLY RECAP*
_13 Jul – 19 Jul 2026_

Quiet week — no picks put up. No-bet days protect the record.

Every result on the record, wins and losses alike.

──────────────────
📲 Join Telegram for daily picks
R18 · Gamble responsibly · Problem Gambling Foundation NZ: 0800 664 262
```
