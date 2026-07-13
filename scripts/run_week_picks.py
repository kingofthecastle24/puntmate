"""Generate this week's real NRL picks — Round 19, 10-12 July 2026."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from generate_picks_image import generate_carousel, generate_multi_images

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── SINGLE: Melbourne Storm to Win ─────────────────────────────────────────────
single = {
    "match": "Storm vs Titans",
    "home_team": "Melbourne Storm",
    "away_team": "Gold Coast Titans",
    "selection": "Storm to Win",
    "odds": "1.40",
    "market": "Head to Head",
    "sport_label": "NRL 2026",
    "sport_tag": "NRL",
    "cover_theme": "Banker of the Day",
    "analysis": "Storm are the benchmark at AAMI Park — one of the most dominant home records in the competition. Titans are winless away in seven straight. Back the class side.",
    "confidence": 4,
    "riskTagline": "LOW RISK · BANKER PLAY · BACK THE STORM",
    "big_game": False,
}

paths = generate_carousel(single, OUTPUT_DIR)
print("Single pick cards:")
for p in paths:
    print(" ", p)

# ── MULTI: 3-leg NRL home treble ───────────────────────────────────────────────
legs = [
    {"match": "Storm vs Titans",    "selection": "Storm to Win",       "market": "H2H", "odds": "1.40"},
    {"match": "Tigers vs Warriors", "selection": "Warriors to Win",    "market": "H2H", "odds": "1.40"},
    {"match": "Dolphins vs Sharks", "selection": "Dolphins to Win",    "market": "H2H", "odds": "1.52"},
]

meta = {
    "palette": "night",
    "coverKicker": "MULTI MONDAY",
    "analysis": "Three home-side plays across the NRL round. Storm and Warriors both face bottom-half opponents on their own patch. Dolphins sneak in at 1.52 as genuine value against the Sharks.",
    "confidence": 3,
    "confidenceLabel": "MODERATE",
    "riskTagline": "HIGHER RISK · BIGGER RETURN · HOME TREBLE",
    "handle": "@puntmatenz",
    "multiType": "Multi",
    "stake": "10",
    "combinedOdds": "$2.98",
}

mpaths = generate_multi_images(legs, meta, OUTPUT_DIR)
print("\nMulti pick cards:")
for p in mpaths:
    print(" ", p)
