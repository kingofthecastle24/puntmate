"""
generate_pick.py — Uses Claude Sonnet to generate 3 picks per match (Investor/Punter/Gambler)
"""

import anthropic
import json
import os

from fetch_news import fetch_news

SPORT_LABELS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026 🌍",
    "rugbyleague_nrl": "NRL 🏉",
    "basketball_nba": "NBA 🏀",
    "rugbyunion_super_rugby": "Rugby 🏉",
    "tennis_atp_french_open": "Tennis ATP 🎾",
    "tennis_wta_french_open": "Tennis WTA 🎾",
}

# --- Personality Profiles ---

PERSONALITIES = {
    "investor": {
        "label": "Investor",
        "emoji": "📊",
        "system": """You are PuntMate NZ — the INVESTOR personality.
You are disciplined, methodical, and cold-blooded. You only back picks where the probability is strongly in your favour. You prefer shorter odds (1.40-2.20) backed by solid evidence: recent form, head-to-head history, home advantage, injury news. You never chase value just for the sake of big returns. Your goal is consistent, steady profit over time — grinding out a positive ROI.
Write in calm, analytical NZ English. No hype. Just logic.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Pick the most statistically probable outcome. Prefer odds between 1.40 and 2.20. Avoid underdogs unless there is overwhelming evidence. Be conservative and precise in your reasoning.",
    },
    "punter": {
        "label": "Punter",
        "emoji": "🎯",
        "system": """You are PuntMate NZ — the PUNTER personality.
You're the everyday NZ sports bettor — you follow the games, you know the teams, and you back what feels right based on form, vibe, and a bit of gut instinct. You're not chasing massive odds but you're not playing it ultra-safe either. You want good value at reasonable odds (1.80-3.50). You write in casual, punchy NZ English — like you're texting your mate about a bet.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Pick based on a balance of form, value and gut feel. Target odds between 1.80 and 3.50. Be casual and direct in your reasoning. Sound like a knowledgeable mate giving a tip.",
    },
    "gambler": {
        "label": "Gambler",
        "emoji": "🎰",
        "system": """You are PuntMate NZ — the GAMBLER personality.
You live for the upset. You back long shots, underdogs, and bold calls. You're chasing big returns and you're not afraid to look stupid. If there's any reason — any at all — to back the underdog or an unlikely outcome, you'll find it and back it with conviction. You prefer odds of 2.50 and above. You write with energy and confidence, like someone who's already spending the winnings.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Back the underdog or the less obvious pick if there is any reason to. Target odds of 2.50 or higher. Look for an upset angle — injury to the favourite, recent poor form, high-pressure game. Be bold and exciting in your reasoning.",
    },
}


def _build_prompt(match, sport_label, news_context, personality_key):
    """Build the user prompt for a specific personality."""
    p = PERSONALITIES[personality_key]
    odds = match['odds']

    odds_text = f"Home ({match['home_team']}): {odds['home']}"
    odds_text += f", Away ({match['away_team']}): {odds['away']}"
    if odds.get('draw'):
        odds_text += f", Draw: {odds['draw']}"

    news_block = ""
    if news_context:
        news_block = f"\nTeam News & Context:\n{news_context}\n"

    return f"""Match: {match['match']}
Sport: {sport_label}
Kickoff: {match['kickoff']}
Current odds: {odds_text}{news_block}

Your personality: {p['label']} — {p['guidance']}

Analyse this match and generate your pick. Return this exact JSON:
{{
  "match": "{match['match']}",
  "sport": "{sport_label}",
  "personality": "{personality_key}",
  "pick": "team name or Over/Under/Draw",
  "market": "Head to Head or Total or Handicap",
  "odds": "2.10",
  "reasoning": "2-3 sentences in your personality voice. What makes this pick right for your style?",
  "confidence": "High or Medium or Low",
  "emoji": "single emoji that fits the pick energy"
}}"""


def generate_pick_for_personality(client, match, sport_label, news_context, personality_key):
    """Generate a single pick for one personality. Returns dict or None."""
    p = PERSONALITIES[personality_key]
    prompt = _build_prompt(match, sport_label, news_context, personality_key)

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=400,
            system=p["system"],
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text
        try:
            pick = json.loads(text)
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                pick = json.loads(text[start:end])
            else:
                raise
        pick['personality'] = personality_key  # ensure it's set
        return pick
    except Exception as e:
        print(f"    Error ({personality_key}): {e}")
        return None


def generate_picks_for_matches(matches):
    """
    Generate Investor + Punter + Gambler picks for each match.
    Returns list of picks (up to 3 per match).
    """
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    all_picks = []

    for match in matches:
        sport_label = SPORT_LABELS.get(match['sport'], match['sport'])
        print(f"\nMatch: {match['match']} ({sport_label})")

        # Fetch news once per match
        try:
            news_context = fetch_news(match)
            if news_context:
                print(f"  News: {len(news_context.splitlines())} headlines")
        except Exception:
            news_context = ""

        for personality_key in PERSONALITIES:
            print(f"  [{personality_key}]", end=" ")
            pick = generate_pick_for_personality(
                client, match, sport_label, news_context, personality_key
            )
            if pick:
                all_picks.append(pick)
                print(f"→ {pick['pick']} @ {pick['odds']} ({pick['confidence']})")
            else:
                print("→ skipped")

    return all_picks
