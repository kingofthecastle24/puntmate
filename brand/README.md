# PuntMate Brand Kit

Everything needed to produce on-brand PuntMate content — logo, favicon, colour/type
system, and editable templates for every platform. Market: **New Zealand** (R18).

Drop this folder into Claude / Cowork and point it at this README. Read
`BRAND-GUIDELINES.md` for the full system.

---

## ⚠️ THE ONE RULE: never post the same format twice

Every post must look different from the last. The feed should never show two
identical-looking posts in a row. Before publishing, change **at least two** of these:

1. **Look** — `Betslip Night` (dark) ↔ `Matchday Print` (loud cream/red)
2. **Accent palette** (Night look only) — green → blue → amber → pink
3. **Cover theme** — Tip of the Week → Multi Monday → Daily Pick → Banker of the Day → Value Alert

Suggested weekly rotation (example — vary it, don't follow rigidly):

| Day | Look | Cover theme | Accent |
|-----|------|-------------|--------|
| Mon | Matchday Print | Multi Monday | — |
| Tue | Betslip Night | Value Alert | blue |
| Wed | Betslip Night | Daily Pick | amber |
| Thu | Matchday Print | Banker of the Day | — |
| Fri | Betslip Night | Tip of the Week | pink |
| Sat | Matchday Print | Daily Pick | — |
| Sun | Betslip Night | Value Alert | green |

Keep a short log of the last 5 posts (look + theme + accent) and make sure the next
post doesn't repeat that combination.

---

## What's in here

```
PuntMate Brand Kit/
├── README.md                     ← you are here
├── BRAND-GUIDELINES.md           ← full brand system (text)
├── Brand Guidelines.dc.html      ← designed version of the guidelines
├── Logo/
│   ├── puntmate-icon-badge.svg/.png     circle badge + value arrow
│   ├── puntmate-icon-glyph.svg/.png     value arrow only
│   ├── puntmate-wordmark.svg/.png       "PUNTMATE" text
│   ├── puntmate-lockup.svg/.png         badge + wordmark (default logo)
│   ├── puntmate-favicon-512.png         app icon / favicon (large)
│   └── puntmate-favicon-32.png          favicon (browser tab)
└── Templates/
    ├── PuntMate Social Templates.dc.html          Post / Story / Cover / Banner / Avatar / Carousel slide
    ├── PuntMate Bet Post - Betslip Night.dc.html  3-slide carousel, dark look
    ├── PuntMate Bet Post - Matchday Print.dc.html 3-slide carousel, loud look
    ├── PuntMate Bet Post - Multi.dc.html           multi / same-game multi, 2–5 legs
    ├── PuntMate Results.dc.html                    results / recap wrap (strike rate + P/L)
    └── PuntMate Site Foundations.dc.html          mobile web pages
```

## Brand consistency (locked)
- **Wordmark**: always the Archivo Black lockup — `PUNT` in white, `MATE` in the accent
  colour (green by default). Same everywhere: banner, posts, site, avatar. Never the
  letter-spaced version.
- **Handle**: **@puntmatenz** on every asset.
- **Logo mark**: the value arrow in the dark circle badge (see /Logo).

## Formats → platforms

| Template / asset | Size | Use for |
|---|---|---|
| Instagram Post | 1080×1080 | IG feed, Facebook feed |
| Instagram / TikTok Story | 1080×1920 | IG Story, TikTok, FB Story, Reels cover |
| Facebook Cover | 820×312 | Facebook page banner |
| Social Preview / Banner | 1280×640 | GitHub, LinkedIn, X/Twitter, website OG image |
| Profile Picture | 1080×1080 | IG / FB / TikTok avatar (circle-safe) |
| Carousel Slide | 1080×1350 | single 4:5 slide |
| Betslip Night carousel | 3× 1080×1350 | full IG carousel, dark look |
| Matchday Print carousel | 3× 1080×1350 | full IG carousel, loud look |
| Multi carousel | 3× 1080×1350 | 2–5-leg multi — Cover / The Legs / The Breakdown |
| Results / recap | 2× 1080×1350 | settled wrap — auto strike-rate + units P/L, WON/LOST/VOID |
| favicon 512 / 32 | 512 / 32 | website favicon, app icon |

## How to make a post

1. Pick a look + cover theme + accent that does **not** repeat the last post (see the rule above).
2. Open the template `.dc.html` in a browser. Edit fields in the **Tweaks panel** (top-right):
   `matchup, sportTag, market, selection, odds, oddsNote, insight` — and for the
   carousels also `competition, analysis, confidence (1–5), riskTagline, coverTheme`.
3. Every field is editable and the layout flexes to fit — longer/shorter names, odds,
   and analysis all reflow.
4. Export each canvas (screenshot / 1080-wide PNG) and post to the matching platform.
5. Keep the NZ compliance line on every post: **R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz**

## Paste-in prompt for Cowork

> This is my PuntMate brand kit — read README.md and BRAND-GUIDELINES.md first.
> When I give you a new bet (matchup, sport, market, selection, odds, a one-line insight,
> a longer analysis, and a confidence 1–5), build the post. IMPORTANT: never use the same
> look/theme/accent combination as the previous post — rotate per the "never post the same
> format twice" rule. Update the template's props, then export the Instagram Post, the
> Instagram/TikTok Story, and the 3-slide carousel. For a multi (2–5 legs) use the Multi
> template — enter one leg per line as `Match | Selection | Odds` and the combined odds
> auto-calculate. Always keep the NZ compliance line and the @puntmatenz handle.
