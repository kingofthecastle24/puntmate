"""
fetch_news.py — Fetches recent news/form context for each match, then runs it
through research_validator before handing anything back to the pick engine.

FIXED BUG (root cause of the France/Spain contradiction): the old Google News
RSS fallback fired whenever ESPN returned nothing, and it hardcoded the query
as "{team} NRL 2025" regardless of the match's actual sport. For a FIFA World
Cup fixture between France and Spain, that meant searching for NRL content
about "France" and "Spain" — literally rugby league headlines — and treating
whatever came back as relevant research. That contaminated research is very
likely what led the LLM to write reasoning that contradicted its own pick.

Now: the RSS query is sport-aware (built from a sport keyword, not a fixed
"NRL 2025" string), and everything returned — from ESPN or RSS — is passed
through research_validator.validate_snippets() before use. Rejected sources
are recorded as warnings (visible internally, never in public copy) and never
reach the LLM prompt.
"""

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote

from research_validator import validate_snippets, assess_evidence_strength

HEADERS = {"User-Agent": "Mozilla/5.0"}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

ESPN_SPORT_MAP = {
    "soccer_fifa_world_cup": "soccer/fifa.world",
}

# Sport-aware search keyword used to build the Google News RSS query. This
# replaces the old hardcoded "NRL 2025" suffix — every sport now searches for
# its own competition, not rugby league.
RSS_SPORT_KEYWORD = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026 football",
    "rugbyleague_nrl": "NRL 2026",
    "rugbyunion_super_rugby": "Super Rugby Pacific",
    "mma_mixed_martial_arts": "UFC MMA",
    "tennis_atp_wimbledon": "Wimbledon ATP tennis",
    "tennis_wta_wimbledon": "Wimbledon WTA tennis",
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
    Returns a dict:
      {
        "text": "short context string for the prompt, or ''",
        "accepted_count": int,
        "warnings": [str, ...],   # rejected/irrelevant sources, internal-only
        "confidence_ceiling": "HIGH" | "MODERATE" | "LOW",
      }
    match dict keys: sport, home_team, away_team
    """
    sport_key = match.get("sport", "")
    home = match.get("home_team", "")
    away = match.get("away_team", "")

    raw_snippets = []

    espn_path = ESPN_SPORT_MAP.get(sport_key)
    if espn_path:
        for team in [home, away]:
            raw_snippets.extend(_espn_news(espn_path, team))

    if not raw_snippets:
        rss_keyword = RSS_SPORT_KEYWORD.get(sport_key, sport_key.replace("_", " "))
        for team in [home, away]:
            raw_snippets.extend(_google_rss_news(f"{team} {rss_keyword}")[:2])

    # Dedupe before validation.
    seen = set()
    unique_raw = []
    for s in raw_snippets:
        if s and s not in seen:
            seen.add(s)
            unique_raw.append(s)

    accepted, warnings = validate_snippets(
        unique_raw, sport=sport_key, home_team=home, away_team=away,
    )
    accepted = accepted[:3]

    confidence_ceiling, ceiling_warnings = assess_evidence_strength(accepted)
    warnings = warnings + ceiling_warnings

    text = "\n".join(f"- {s}" for s in accepted)

    return {
        "text": text,
        "accepted_count": len(accepted),
        "warnings": warnings,
        "confidence_ceiling": confidence_ceiling,
    }
