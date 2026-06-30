"""
fetch_news.py — Fetches recent news/form context for each match.
No API key required. Sources:
  - ESPN hidden API (NBA, ATP, WTA tennis)
  - Google News RSS (NRL, fallback for all sports)
Returns a short text snippet to inject into the Claude prompt.
"""

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote

HEADERS = {"User-Agent": "Mozilla/5.0"}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

ESPN_SPORT_MAP = {
    "basketball_nba": "basketball/nba",
    "tennis_atp_french_open": "tennis/atp",
    "tennis_wta_french_open": "tennis/wta",
    "soccer_fifa_world_cup": "soccer/fifa.world",
}


def _espn_news(sport_path, team_or_player):
    """Fetch top 2 ESPN articles mentioning this team/player."""
    url = f"{ESPN_BASE}/{sport_path}/news"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if not resp.ok:
            return []
        articles = resp.json().get("articles", [])
        hits = []
        name_lower = team_or_player.lower()
        for a in articles[:20]:
            headline = a.get("headline", "")
            desc = a.get("description", "")
            cats = " ".join(
                c.get("description", "") for c in a.get("categories", [])
            ).lower()
            if name_lower in cats or name_lower in headline.lower():
                hits.append(headline)
            if len(hits) >= 2:
                break
        return hits
    except Exception:
        return []


def _google_rss_news(query):
    """Fetch top 2 Google News RSS headlines for a query."""
    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-NZ&gl=NZ&ceid=NZ:en"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if not resp.ok:
            return []
        root = ET.fromstring(resp.content)
        items = root.findall(".//item/title")
        return [i.text for i in items[:2] if i.text]
    except Exception:
        return []


def fetch_news(match):
    """
    Returns a short context string for the match, or "" if nothing found.
    match dict keys: sport, home_team, away_team
    """
    sport_key = match.get("sport", "")
    home = match.get("home_team", "")
    away = match.get("away_team", "")

    snippets = []

    espn_path = ESPN_SPORT_MAP.get(sport_key)
    if espn_path:
        for team in [home, away]:
            hits = _espn_news(espn_path, team)
            snippets.extend(hits)

    # NRL: always use Google RSS
    if sport_key == "rugbyleague_nrl" or not snippets:
        for team in [home, away]:
            hits = _google_rss_news(f"{team} NRL 2025")
            snippets.extend(hits[:1])

    if not snippets:
        return ""

    # Deduplicate and cap
    seen = set()
    unique = []
    for s in snippets:
        if s not in seen:
            seen.add(s)
            unique.append(s)
        if len(unique) >= 3:
            break

    return "\n".join(f"- {s}" for s in unique)
