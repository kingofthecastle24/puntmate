"""
generate_pick.py — Uses Claude Sonnet to select ONE best pick per personality (Investor/Punter/Gambler)
across all available matches for the day.
"""

import anthropic
import json
import os

from fetch_news import fetch_news

SPORT_LABELS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026",
    "rugbyleague_nrl": "NRL",
    "basketball_nba": "NBA",
    "rugbyunion_super_rugby": "Rugby",
    "tennis_atp_french_open": "Tennis ATP",
    "tennis_wta_french_open": "Tennis WTA",
}

# --- Personality Profiles ---

PERSONALITIES = {
    "investor": {
        "label": "Investor",
        "emoji": "📊",
        "system": """You are PuntMate NZ — the INVESTOR personality.
You are disciplined, methodical, and cold-blooded. You only back picks where the probability is strongly in your favour. You prefer shorter odds (1.40–2.20) backed by solid evidence: recent form, head-to-head history, home advantage, injury news. You never chase value just for the sake of big returns. Your goal is consistent, steady profit over time.
Write in calm, analytical NZ English. No hype. Just logic.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Pick the SINGLE most statistically probable outcome from ALL matches below. Prefer odds 1.40–2.20. Be conservative and precise. One pick only.",
        "odds_hint": "1.40–2.20",
    },
    "punter": {
        "label": "Punter",
        "emoji": "🎯",
        "system": """You are PuntMate NZ — the PUNTER personality.
You're the everyday NZ sports bettor — you follow the games, you know the teams, and you back what feels right based on form, vibe, and a bit of gut instinct. You want good value at reasonable odds (1.80–3.50). Casual, punchy NZ English — like texting your mate about a bet.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Pick the SINGLE best value bet from ALL matches below. Target odds 1.80–3.50. Balance of form, value, and gut feel. One pick only.",
        "odds_hint": "1.80–3.50",
    },
    "gambler": {
        "label": "Gambler",
        "emoji": "🎰",
        "system": """You are PuntMate NZ — the GAMBLER personality.
You live for the upset. You back long shots, underdogs, and bold calls. You're chasing big returns and not afraid to look stupid. If there's any reason to back the underdog, you'll find it. Odds 2.50+. Write with energy and confidence — like you're already spending the winnings.
Always return ONLY valid JSON, no other text.""",
        "guidance": "Pick the SINGLE boldest upset/longshot from ALL matches below. Target odds 2.50+. Find the best underdog angle. One pick only.",
        "odds_hint": "2.50+",
    },
}


def _build_multi_match_prompt(matches, match_news, personality_key):
    """Build a prompt that gives Claude all matches at once, asking for the single best pick."""
    p = PERSONALITIES[personality_key]

    match_blocks = []
    for i, match in enumerate(matches, 1):
        sport_label = SPORT_LABELS.get(match['sport'], match['sport'])
        odds = match['odds']
        odds_text = f"Home ({match['home_team']}): {odds['home']}"
        odds_text += f", Away ({match['away_team']}): {odds['away']}"
        if odds.get('draw'):
            odds_text += f", Draw: {odds['draw']}"

        news = match_news.get(match['match'], "")
        news_block = f"\n  News: {news}" if news else ""

        match_blocks.append(
            f"Match {i}: {match['match']}\n"
            f"  Sport: {sport_label} | Kickoff: {match['kickoff']}\n"
            f"  Odds — {odds_text}{news_block}"
        )

    matches_text = "\n\n".join(match_blocks)

    return f"""Today's available matches:

{matches_text}

Your role: {p['label']} — {p['guidance']}
Target odds: {p['odds_hint']}

Review ALL matches above. Choose the SINGLE best pick that fits your personality profile. Return this exact JSON:
{{
  "match": "Home Team vs Away Team (exact match name from above)",
  "sport": "sport label",
  "personality": "{personality_key}",
  "pick": "team name, Over X.X, Under X.X, or Draw",
  "market": "Head to Head or Total or Handicap",
  "odds": "2.10",
  "reasoning": "2-3 sentences in your personality voice explaining why this is THE pick today",
  "confidence": "High or Medium or Low",
  "emoji": "single emoji"
}}"""


def generate_picks_for_matches(matches):
    """
    Generate ONE Investor pick, ONE Punter pick, ONE Gambler pick from all available matches.
    Returns list of 3 picks (one per personality).
    """
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    # Fetch news for all matches upfront
    print("  Fetching news context...")
    match_news = {}
    for match in matches:
        try:
            news = fetch_news(match)
            if news:
                match_news[match['match']] = news
        except Exception:
            pass

    all_picks = []

    for personality_key, p in PERSONALITIES.items():
        print(f"\n  [{p['label']}] Selecting best pick from {len(matches)} matches...", end=" ")

        prompt = _build_multi_match_prompt(matches, match_news, personality_key)

        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=500,
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

            pick['personality'] = personality_key  # ensure correct
            # Enrich with home/away team if match is found
            for m in matches:
                if m['match'] == pick.get('match'):
                    pick['home_team'] = m['home_team']
                    pick['away_team'] = m['away_team']
                    pick['sport_key'] = m['sport']
                    break

            all_picks.append(pick)
            print(f"→ {pick['match']} | {pick['pick']} @ {pick['odds']} ({pick['confidence']})")

        except Exception as e:
            print(f"→ ERROR: {e}")

    return all_picks
