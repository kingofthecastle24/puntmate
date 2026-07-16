"""
fetch_news.py — Fetches recent news/form context for each match, then runs it
through research_validator before handing anything back to the pick engine.

FIXED BUG (root cause of the France/Spain contradiction): the old Google News
RSS fallback fired whenever ESPN returned nothing, and it hardcoded the query
as "{team} NRL 2025" regardless of the match's actual sport. Now the RSS
query is sport-aware, and everything returned — from ESPN or RSS — is passed
through research_validator.validate_snippets() before use. Rejected sources
are recorded as warnings (visible internally, never in public copy) and never
reach the LLM prompt.

Phase 1 (research depth widening): previously ESPN was only ever tried for
the World Cup, and RSS was only used as a fallback when ESPN returned
nothing — meaning NRL/rugby/MMA/tennis relied on a thin 1-2-headline scrape
in practice. Now: ESPN is attempted for every sport that has a plausible
ESPN site-API path (best-effort — ESPN's site API isn't officially
documented, so these paths are educated guesses; any that are wrong just
return nothing via the existing try/except, same as before), AND RSS always
runs too (not just as a fallback) so results are combined rather than
either/or. A match-level query (both team names together) is added alongside
the existing per-team queries, since preview/analysis articles that discuss
both sides tend to be more relevant than generic single-team news.
"""

import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote

from research_validator import validate_snippets, assess_evidence_strength

HEADERS = {"User-Agent": "Mozilla/5.0"}
ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Best-effort ESPN site-API sport/league paths. Unverifiable from this
# sandbox (ESPN is network-blocked here) — if any path is wrong it will 404
# or return an empty article list, which _espn_news() already treats as "no
# results" and falls through to RSS, so a wrong guess costs nothing. Worth
# confirming against real traffic on the next GitHub Actions run.
ESPN_SPORT_MAP = {
    "soccer_fifa_world_cup":  "soccer/fifa.world",
    "rugbyleague_nrl":        "rugby-league/nrl",
    "rugbyunion_super_rugby": "rugby/super-rugby-pacific",
    "mma_mixed_martial_arts": "mma/ufc",
    "tennis_atp_wimbledon":   "tennis/atp",
    "tennis_wta_wimbledon":   "tennis/wta",
}

# Sport-aware search keyword used to build the Google News RSS query.
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

    # ESPN, if this sport has a mapped path — tried for every sport now, not
    # just the World Cup.
    espn_path = ESPN_SPORT_MAP.get(sport_key)
    if espn_path:
        for team in [home, away]:
            raw_snippets.extend(_espn_news(espn_path, team))

    # RSS always runs too (combined with ESPN, not fallback-only) — per-team
    # queries plus one match-level query for preview/analysis articles that
    # mention both sides.
    rss_keyword = RSS_SPORT_KEYWORD.get(sport_key, sport_key.replace("_", " "))
    for team in [home, away]:
        raw_snippets.extend(_google_rss_news(f"{team} {rss_keyword}")[:2])
    if home and away:
        raw_snippets.extend(_google_rss_news(f"{home} {away} {rss_keyword}")[:2])

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
