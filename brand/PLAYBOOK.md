# PuntMate Playbook — what to use, when, and what to change

Written from the tipster's chair: pick the right template, know exactly which fields to
edit, and never repeat a format. Full brand rules live in BRAND-GUIDELINES.md.

---

## Which template for which post

| You want to post… | Use | Why |
|---|---|---|
| One strong pick, full story | **Bet Post – Betslip Night** (dark) | Everyday default. Cover → The Tip → The Breakdown. |
| One pick, loud/hype tone | **Bet Post – Matchday Print** (cream/red) | Big-match energy, finals, grudge games. Alternate with Night so the feed varies. |
| A multi / same-game multi (2–5 legs) | **Bet Post – Multi** | Combined odds auto-calc. Great for Multi Monday, weekend accumulators. |
| A results / recap wrap | **Results** | Builds trust. Auto strike-rate + units P/L, WON/LOST/VOID. Post after games settle. |
| A quick single graphic (no carousel) | **Social Templates → IG Post** (1080×1080) | Fast one-slide pick for feed. |
| A story / TikTok | **Social Templates → Story** (1080×1920) | Same pick, vertical. Add "SWIPE UP". |
| Page/channel banner | **Social Templates → FB Cover** / **Banner 1280×640** | Cover = Facebook page. Banner = GitHub / LinkedIn / X / website OG. |
| Profile picture | **Social Templates → Avatar** | Circle-safe icon for IG / FB / TikTok. |
| Website favicon / app icon | **Logo/puntmate-favicon-512 / -32** | Drop straight in, no editing. |

---

## What you can change in each template (Tweaks panel, top-right)

### Bet Post – Betslip Night & Matchday Print (single pick, 3 slides)
- **Cover** section: `coverTheme` — Tip of the Week · Multi Monday · Daily Pick · Banker of the Day · Value Alert. Changes the kicker + big headline.
- **Pick** section: `matchup`, `sportTag`, `market`, `selection`, `odds`, `oddsNote`, `insight`, `handle`. (Print also has `selectionShort` for the compact strip.)
- **Breakdown** section: `competition`, `analysis` (the reasoning paragraph), `confidence` (1–5 slider → the dots meter), `confidenceLabel` (LOW / MODERATE… risk word), `riskTagline` (the three chips — split on "·").
- **Style** (Night only): `palette` — green / blue / amber / pink.

### Bet Post – Multi (2–5 legs)
- **Legs**: `legs` — one leg per line as `Match | Selection | Odds` (or `Match | Selection | Market | Odds`). 2 to 5 lines. `multiType` (label e.g. "Same-Game Multi"). `combinedOdds` — leave blank to auto-calculate, or type your own.
- **Cover**: `coverKicker` (e.g. MULTI MONDAY).
- **Breakdown**: `analysis`, `confidence`, `confidenceLabel`, `riskTagline`, `stake` (auto-shows the return, e.g. "$10 returns $68.54").
- **Style**: `palette`.

### Results (recap, 2 slides)
- **Results**: `results` — one settled pick per line as `Match | Selection | Odds | WON` (or LOST / VOID). Wins, losses, strike rate, units P/L and best win all auto-calculate (1 unit per pick). `period` (e.g. THIS WEEK / ROUND 18), `summary` (one-line wrap).
- **Brand/Style**: `handle`, `palette`.
- When to use: after your picks settle — weekly wrap or a round recap. This is your trust-builder; post it consistently.

### Social Templates (Post / Story / Cover / Banner / Avatar / Carousel)
- **Pick**: `matchup`, `sportTag`, `market`, `selection`, `odds`, `oddsNote`, `insight`.
- **Brand**: `handle`, `tagline` (used on Cover + Banner).
- **Style**: `palette`.
- Avatar, favicon and the banner are evergreen — set once, reuse.

Every text field reflows if you make it longer or shorter, and every single colour/word
is directly editable in the canvas too. Nothing is baked in except the logo and layout.

---

## Rules that never change
- **Wordmark**: Archivo Black lockup, PUNT (white) + MATE (accent). Same everywhere.
- **Handle**: @puntmatenz.
- **NZ compliance line** on every post: R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz
- **Never post the same format twice** — change at least two of look / accent / cover theme each time (see README rotation table).

---

## A typical week (example — vary it)
- **Mon** Multi (Multi Monday, amber)
- **Tue** Betslip Night single (Value Alert, blue)
- **Wed** Matchday Print single (Banker of the Day)
- **Thu** Betslip Night single (Daily Pick, pink)
- **Fri** Matchday Print single (Tip of the Week)
- **Sat** Multi (green) + Stories through the day
- **Sun** Betslip Night single (Daily Pick, green)

Keep a note of the last 5 posts (look + theme + accent) so the next one doesn't repeat.
