# PuntMate Brand Guidelines

## What this kit is for
Everything needed to keep new content on-brand: logo files, colour/type system, and
live editable templates for social posts and site pages. See "Brand Guidelines.dc.html"
for the designed version of this doc. Market: New Zealand.

## Logo
The mark is the "value arrow" — a rising trend line with an arrowhead (upward momentum /
finding the value). Files in /Logo — SVG (vector) and PNG (transparent background):
- puntmate-icon-badge (.svg/.png) — dark circle badge with the value arrow. Default icon
  use: profile pictures, favicons, small placements.
- puntmate-icon-glyph (.svg/.png) — the value arrow alone, no circle.
- puntmate-wordmark (.svg/.png) — "PUNTMATE" text only (PUNT white, MATE green), Archivo Black.
- puntmate-lockup (.svg/.png) — badge + wordmark combined. Default full logo.
- puntmate-favicon-512.png — solid dark rounded tile with the arrow. App icon / large favicon.
- puntmate-favicon-32.png — 32px favicon for the browser tab.

Clear space: leave at least the icon's own radius as padding on every side.
Minimum size: 32px for the icon, 120px wide for the wordmark.
Never stretch, rotate, recolour the arrow outside the approved palette, or place on a
busy photo without a dark scrim behind it.

## Colour
- Ink Black #0B0F0D — base background
- Surface #111815 — cards / panels
- Signal Green #35E07E — primary accent (odds, CTAs, the arrow)
- Paper White #EAF7EF — primary text on dark

Accent rotation (keep Ink Black + Paper White fixed, swap only the accent):
green #35E07E · blue #3DB2FF · amber #FFC145 · pink #FF4FA3
Rotate the accent each post so the feed doesn't look identical every time. Never mix
two accents in one asset.

Matchday Print look uses its own fixed palette: Cream #F4EEE2, Ink #16130F,
Red #E8402A, Yellow #FFD400.

## Type — two systems
Betslip Night (dark — website, social posts, stories):
- Archivo (900/Black) — the PUNTMATE wordmark + lockups
- Space Grotesk (700/500/400) — headlines, selection names, body copy, card content
- Space Mono (400/700) — odds figures, labels, tags, timestamps — uppercase, wide tracking

Matchday Print (loud cream/red tabloid carousel):
- Anton — giant stacked headlines (BEST VALUE BET, the selection name)
- Barlow Condensed (600/700) — kickers, subheads, reasoning line, footer bars
- Archivo (900/Black) — shared wordmark + FOLLOW line

## Consistency (locked)
- Wordmark: always the Archivo Black lockup — PUNT (white) + MATE (accent green). Same
  everywhere; never the letter-spaced version.
- Handle: @puntmatenz on every asset.

## Voice
Short, confident, one pick + one line of reasoning. Talk like a mate with a good tip,
not bookmaker ad copy. Never promise a result — frame as value/analysis.

## NZ compliance (non-negotiable, every format)
Every post must carry: "R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz"
(short placements may use "R18 · Gamble responsibly · 0800 654 655").

## Rotation rule — never post the same format twice
The feed must never show two identical-looking posts in a row. Before every post, change
AT LEAST TWO of: (1) look — Betslip Night ↔ Matchday Print; (2) accent palette (Night
only) — green/blue/amber/pink; (3) cover theme — Tip of the Week / Multi Monday / Daily
Pick / Banker of the Day / Value Alert. Keep a short log of the last 5 posts and don't
repeat that look+theme+accent combination. See README.md for a sample weekly rotation.

## Templates + formats
Live, editable templates — open the .dc.html file, edit fields in the Tweaks panel (top
right), rotate look/palette/theme, then screenshot/export each canvas. Every field is
editable and the layout reflows to fit longer or shorter text:

- Templates/PuntMate Social Templates.dc.html — single-format pack:
  - Instagram Post — 1080 × 1080 (also Facebook feed)
  - Instagram / TikTok Story — 1080 × 1920 (IG + TikTok + FB Story + Reels cover)
  - Facebook Cover — 820 × 312 (evergreen banner, not pick-specific)
  - Social Preview / Banner — 1280 × 640 (GitHub, LinkedIn, X/Twitter, website OG image)
  - Profile Picture — 1080 × 1080 (IG / FB / TikTok avatar, safe-zone circle)
  - Carousel Slide — 1080 × 1350 (single slide, 4:5)
- Templates/PuntMate Bet Post - Betslip Night.dc.html — 3-slide carousel, dark look (1A):
  Cover → The Tip → The Breakdown. Tweaks: coverTheme, pick fields, competition, analysis,
  confidence (1–5), confidenceLabel, riskTagline, palette.
- Templates/PuntMate Bet Post - Matchday Print.dc.html — 3-slide carousel, loud look (1B), same fields.
- Templates/PuntMate Bet Post - Multi.dc.html — 2–5-leg multi carousel (Cover → The Legs → The
  Breakdown). Enter legs one per line as "Match | Selection | Odds"; combined odds auto-calculate.
- Templates/PuntMate Site Foundations.dc.html — mobile web Home / All Tips / Tip Detail pages

## Workflow for a new pick (for Claude / Cowork)
1. Pick a look + cover theme + accent that does NOT repeat the previous post (rotation rule above).
2. Update: matchup, sportTag, market, selection, odds, insight (and oddsNote / analysis / confidence where present).
3. Export each canvas and post to the matching platform. Keep the NZ compliance line, every time.
