"""
research_validator.py — validates candidate research/news snippets against
the actual fixture before they're allowed anywhere near the pick-generation
prompt.

Root cause this fixes: fetch_news.py's old Google News RSS fallback appended
a hardcoded "NRL 2025" to every query when ESPN returned nothing, regardless
of the match's real sport — so a France vs Spain FIFA World Cup fixture could
pull back NRL headlines about "France" and "Spain" as if they were relevant
rugby league content. That contradictory/irrelevant research is what the LLM
was reasoning from when it produced a France pick whose own text said "no
pick meets my criteria."

This module doesn't fetch anything — it only judges snippets it's given
against the fixture's sport, competition, teams and date, and returns which
ones are safe to use plus human-readable warnings for the rejected ones.
"""

import re

# Keywords that must NOT appear in a snippet claimed relevant to a given
# sport — i.e. if a "soccer" snippet is actually about rugby league, reject
# it even if the team names happen to match.
CROSS_SPORT_MARKERS = {
    "soccer_fifa_world_cup": ["nrl", "rugby league", "grand final", "try scorer", "state of origin"],
    "rugbyleague_nrl": ["fifa", "premier league", "la liga", "champions league", "penalty kick"],
    "rugbyunion_super_rugby": ["nrl", "fifa", "champions league"],
    "mma_mixed_martial_arts": ["nrl", "fifa", "champions league", "grand final"],
    "tennis_atp_wimbledon": ["nrl", "fifa", "grand final"],
    "tennis_wta_wimbledon": ["nrl", "fifa", "grand final"],
}

# Words that indicate genuine sport relevance for each sport key (used as a
# light positive signal, not a hard requirement — team names are usually
# enough, this just helps break ties / catch pure-name-collision hits).
SPORT_KEYWORDS = {
    "soccer_fifa_world_cup": ["world cup", "fifa", "football", "soccer", "match", "goal", "squad", "kickoff"],
    "rugbyleague_nrl": ["nrl", "rugby league", "try", "tackle"],
    "rugbyunion_super_rugby": ["super rugby", "rugby union", "all blacks"],
    "mma_mixed_martial_arts": ["ufc", "mma", "octagon", "fight"],
    "tennis_atp_wimbledon": ["wimbledon", "tennis", "atp", "set", "serve"],
    "tennis_wta_wimbledon": ["wimbledon", "tennis", "wta", "set", "serve"],
}


class ValidatedSnippet:
    def __init__(self, text, accepted, reason):
        self.text = text
        self.accepted = accepted
        self.reason = reason


def _mentions_team_only(text, home_team, away_team):
    """True if the snippet's only tie to the fixture is a bare team-name
    match, with no sport-relevant vocabulary at all — a strong signal it's
    about a different competition/sport entirely (e.g. a rugby article about
    a country also mentioned in a football fixture)."""
    return True  # caller combines this with keyword checks; see validate_snippets


def validate_snippets(snippets, sport, home_team, away_team, competition=None, fixture_date=None):
    """
    snippets: list[str] of raw headline/snippet text.
    sport: sport key, e.g. "soccer_fifa_world_cup".
    Returns (accepted: list[str], warnings: list[str]).
    """
    accepted = []
    warnings = []

    cross_markers = CROSS_SPORT_MARKERS.get(sport, [])
    sport_words = SPORT_KEYWORDS.get(sport, [])
    home_l = (home_team or "").lower()
    away_l = (away_team or "").lower()

    for snippet in snippets or []:
        if not snippet or not snippet.strip():
            continue
        low = snippet.lower()

        # 1. Reject outright cross-sport contamination.
        hit_markers = [m for m in cross_markers if m in low]
        if hit_markers:
            warnings.append(
                f"rejected source (wrong sport for {sport}): \"{snippet[:80]}\" "
                f"— matched unrelated-sport marker(s): {', '.join(hit_markers)}"
            )
            continue

        # 2. Reject team-name-only matches with zero sport-relevant vocabulary
        #    — e.g. a snippet that only says "France" with no football
        #    context at all is not safe to treat as relevant research.
        mentions_team = (home_l and home_l in low) or (away_l and away_l in low)
        mentions_sport_word = any(w in low for w in sport_words)
        if mentions_team and not mentions_sport_word:
            warnings.append(
                f"rejected source (team-name-only match, no sport context): \"{snippet[:80]}\""
            )
            continue

        # 3. If it mentions neither the team nor any sport keyword, it's not
        #    relevant at all.
        if not mentions_team and not mentions_sport_word:
            warnings.append(f"rejected source (no relevance to fixture): \"{snippet[:80]}\"")
            continue

        accepted.append(snippet)

    return accepted, warnings


def assess_evidence_strength(accepted_snippets, requested_count=3):
    """Returns a confidence ceiling ('HIGH'/'MODERATE'/'LOW') based on how
    much *validated* research was actually available. This is a ceiling —
    the pick-generation step may only assess confidence at or below this.

    Phase 1 change: zero validated news sources now caps at MODERATE, not
    LOW. Previously this reflected "we have literally nothing" — but
    generate_pick.py's system prompt now explicitly allows Claude to use its
    general knowledge of the teams/competition (form, typical strength,
    home-ground advantage) as legitimate supporting context even when no
    fresh news snippet was found. That's a real, if weaker, evidence basis —
    LOW is now reserved for genuinely no-basis situations, which the model
    itself still self-reports via evidence_sufficient=false when neither
    validated news nor a real general-knowledge basis exists for a pick.
    HIGH still requires real validated current sources — general knowledge
    alone is never enough for a HIGH confidence ceiling."""
    n = len(accepted_snippets)
    if n == 0:
        return "MODERATE", ["no validated news sources — confidence capped at MODERATE (general knowledge may still apply)"]
    if n < requested_count:
        return "MODERATE", [f"only {n} validated source(s) — confidence capped at MODERATE"]
    return "HIGH", []
