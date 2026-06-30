"""
generate_pick.py — Uses Claude Haiku to analyse odds and generate a PuntMate pick
"""

import anthropic
import json
import os

SPORT_LABELS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026 🌍",
    "rugbyleague_nrl": "NRL 🏉",
    "basketball_nba": "NBA 🏀",
    "rugbyunion_super_rugby": "Super Rugby 🏉",
}

SYSTEM_PROMPT = """You are PuntMate NZ — a sharp, straight-talking sports betting analyst for New Zealand audiences who bet with TAB NZ.

Your picks are based on value in the odds, not just who's favourite. You sound confident but honest — you acknowledge when confidence is lower. You write in casual NZ English (no slang overdone), direct and punchy.

Always return ONLY valid JSON, no other text."""


def generate_pick(match):
    """Generate a betting pick for a single match. Returns a dict."""
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    sport_label = SPORT_LABELS.get(match['sport'], match['sport'])
    odds = match['odds']

    odds_text = f"Home ({match['home_team']}): {odds['home']}"
    odds_text += f", Away ({match['away_team']}): {odds['away']}"
    if odds.get('draw'):
        odds_text += f", Draw: {odds['draw']}"

    user_prompt = f"""Match: {match['match']}
Sport: {sport_label}
Kickoff: {match['kickoff']}
Current odds: {odds_text}

Analyse this match and generate a pick. Return this exact JSON:
{{
  "match": "{match['match']}",
  "sport": "{sport_label}",
  "pick": "team name or Over/Under/Draw",
  "market": "Head to Head or Total or Handicap",
  "odds": "2.10",
  "reasoning": "2-3 sentences. What makes this value? Any relevant form, injuries, or trends worth mentioning. Casual NZ voice.",
  "confidence": "High or Medium or Low",
  "emoji": "single emoji that fits (🔥 for high confidence, ⚡ for value, ✅ for solid pick)"
}}"""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}]
    )

    try:
        pick = json.loads(message.content[0].text)
        return pick
    except json.JSONDecodeError:
        # Try to extract JSON if there's extra text
        text = message.content[0].text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def generate_picks_for_matches(matches):
    """Generate picks for a list of matches. Returns list of picks."""
    picks = []
    for match in matches:
        try:
            print(f"Generating pick for: {match['match']}")
            pick = generate_pick(match)
            picks.append(pick)
            print(f"  → {pick['pick']} @ {pick['odds']} ({pick['confidence']})")
        except Exception as e:
            print(f"  Error generating pick: {e}")
            continue
    return picks
