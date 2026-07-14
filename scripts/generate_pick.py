"""
generate_pick.py — selects ONE official PuntMate pick (or NO_BET) per run.

This replaces the old three-personality system (investor/punter/gambler each
producing their own pick). That design is what caused a real live-post bug:
three picks could land on the same match, the renderer silently overwrote
files when that happened, and — separately — one personality's own reasoning
text ("no pick meets my criteria... sitting this one out") was still posted
as if it were a live recommendation, because nothing checked the copy against
the classification before it went out.

New flow (matches the pipeline order in the spec):
  1. Claude proposes ONE candidate match + raw evidence (no tone, no verdict —
     just probability estimate, confidence, uncertainty flags, grounded only
     in the odds + validated research it was given).
  2. pick_classifier.classify() deterministically decides RISK
     (STANDARD_PICK / RISKY_PICK / NO_BET) and BET_TYPE (INVESTOR_BET /
     PUNTER_BET / GAMBLER_BET / NO_BET) from that evidence — Claude's own
     opinion of its confidence is capped by how much validated research
     actually backed it (see research_validator.assess_evidence_strength).
  3. Copy (bet-type reason, final explanation, Telegram text, Instagram
     caption) is generated from fixed tone templates + a cleaned one-line
     excerpt of Claude's reasoning, then run through copy_validator before
     anything is accepted.

If nothing clears the bar, this returns a NO_BET result — never three
fallback picks, never a contradiction between the verdict and the copy.
"""

import anthropic
import json
import os
import re

from pick_classifier import Evidence, classify, RISK_NO_BET, BET_NO_BET
from copy_validator import validate_text, CopyValidationError, BANNED_TONE_PHRASES, STAKE_PHRASES

SPORT_LABELS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026",
    "rugbyleague_nrl": "NRL",
    "rugbyunion_super_rugby": "Super Rugby",
    "mma_mixed_martial_arts": "UFC",
    "tennis_atp_wimbledon": "Wimbledon",
    "tennis_wta_wimbledon": "Wimbledon",
}

CONFIDENCE_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2}

SYSTEM_PROMPT = """You are PuntMate NZ — a mate who knows sport, not a financial analyst.
You talk like someone who actually watches the games and has a read on form, not
someone reading off a spreadsheet. Plain NZ English, honest about uncertainty,
never corporate or robotic.

You will be shown today's matches with bookmaker odds and (where available)
validated recent news/form snippets. Your job is ONLY to assess the evidence —
you do NOT decide risk level or bet type, that's calculated separately.

Ground everything ONLY in the odds and news actually given to you. If a match
has no news provided, say so honestly rather than inventing form. Never
mention stake sizes, units, dollar amounts to bet, or bankroll percentages —
that is not your job and must never appear in your reasoning.

Return ONLY valid JSON, no markdown, no extra text."""


def _build_prompt(matches, match_news):
    blocks = []
    for i, m in enumerate(matches, 1):
        odds = m["odds"]
        implied = m.get("implied_probs", {}) or {}
        odds_text = f"Home ({m['home_team']}): {odds['home']} (implied {implied.get('home', 0)*100:.1f}%)"
        odds_text += f", Away ({m['away_team']}): {odds['away']} (implied {implied.get('away', 0)*100:.1f}%)"
        if odds.get("draw"):
            odds_text += f", Draw: {odds['draw']} (implied {implied.get('draw', 0)*100:.1f}%)"

        news = match_news.get(m["match"], {})
        news_text = news.get("text", "")
        news_block = f"\n  Validated news/form:\n{news_text}" if news_text else "\n  Validated news/form: none available"

        blocks.append(
            f"Match {i}: {m['match']}\n"
            f"  Sport: {SPORT_LABELS.get(m['sport'], m['sport'])} | Kickoff: {m['kickoff']}\n"
            f"  Odds — {odds_text}{news_block}"
        )
    matches_text = "\n\n".join(blocks)

    return f"""Today's matches:

{matches_text}

Assess every match. If — and only if — one of them has a genuinely defensible
selection (the evidence actually supports an edge over the bookmaker's
implied probability), return that ONE match. If nothing is defensible, say so.

Return this exact JSON:
{{
  "has_selection": true,
  "match": "exact match name from above",
  "sport": "sport key matching the match",
  "selection": "TEAM NAME, DRAW, Over X.X, or Under X.X",
  "market": "Head to Head",
  "our_probability": 58,
  "evidence_sufficient": true,
  "confidence": "HIGH or MODERATE or LOW — how strong is the evidence you actually have, not how you feel about the team",
  "uncertainty_flags": ["short phrase", "short phrase"],
  "reasoning": "2-3 sentences, plain NZ English, mate-to-mate tone, grounded only in what you were given"
}}

Or, if nothing is defensible today:
{{
  "has_selection": false,
  "reasoning": "1-2 sentences, plain language, on why nothing clears the bar today"
}}"""


def _extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
        raise


def sanitize_reasoning(text):
    """Strip banned tone/staking phrases from a model-generated sentence
    before it's allowed into a template. This is a safety net — the system
    prompt already tells the model not to use this language — not the only
    line of defence (copy_validator still runs after)."""
    cleaned = text
    for phrase in BANNED_TONE_PHRASES + STAKE_PHRASES:
        cleaned = re.sub(re.escape(phrase), "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _one_sentence(text, max_len=160):
    text = text.strip()
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut.rstrip(",.;") + "…"


BET_TYPE_OPENERS = {
    "INVESTOR_BET": "This one's about as close to a sure thing as sport gets — the numbers stack up and the price still pays.",
    "PUNTER_BET": "Solid touch here. Not a lock, but the value's real and the form backs it up.",
    "GAMBLER_BET": "Bold call at a big price — this is a swing, not a certainty, but the upside is real.",
}

BET_TYPE_LABELS = {
    "INVESTOR_BET": "BET TYPE: INVESTOR",
    "PUNTER_BET": "BET TYPE: PUNTER",
    "GAMBLER_BET": "BET TYPE: GAMBLER",
}

RISK_PUBLIC_CAUTION = {
    "RISKY_PICK": "Keep this one light — the value's there but so is the uncertainty.",
}


def build_bet_type_reason(bet_type, reasoning_sentence):
    opener = BET_TYPE_OPENERS.get(bet_type, "")
    return f"{opener} {reasoning_sentence}".strip()


def build_final_explanation(reasoning_sentence, risk, uncertainty_flags):
    parts = [reasoning_sentence]
    if risk == "RISKY_PICK" and uncertainty_flags:
        parts.append("Worth knowing: " + "; ".join(uncertainty_flags[:2]) + ".")
    return " ".join(parts).strip()


def generate_pick_for_matches(matches, match_news):
    """
    matches: list of match dicts from fetch_odds.fetch_upcoming_odds()
    match_news: dict {match_name: fetch_news() result dict}

    Returns a single pick dict with keys:
      has_pick, match, sport, sport_label, home_team, away_team, kickoff,
      selection, market, odds, our_probability, implied_probability, edge_pct,
      risk, bet_type, bet_type_reason, final_explanation, confidence,
      confidence_label, uncertainty_flags, research_warnings
    or {"has_pick": False, "reasoning": "..."} when nothing clears the bar.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = _build_prompt(matches, match_news)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=700,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    result = _extract_json(message.content[0].text)

    research_warnings = []
    for m in matches:
        research_warnings += match_news.get(m["match"], {}).get("warnings", [])

    if not result.get("has_selection"):
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": result.get("reasoning", "Nothing today clears the bar for a defensible pick."),
            "research_warnings": research_warnings,
        }

    match_meta = next((m for m in matches if m["match"] == result.get("match")), {})
    if not match_meta:
        # Model named a match that wasn't in the candidate list at all —
        # can't trust it, treat as NO_BET rather than guessing.
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": "Model returned a selection that didn't match any candidate fixture — treated as no bet.",
            "research_warnings": research_warnings + ["model hallucinated a match not in the candidate list"],
        }

    odds = match_meta["odds"]
    implied = match_meta.get("implied_probs", {}) or {}
    selection_upper = (result.get("selection") or "").upper()
    home = match_meta["home_team"]
    away = match_meta["away_team"]

    if selection_upper == home.upper():
        odds_val = odds.get("home")
        implied_pct = (implied.get("home") or 0) * 100
    elif selection_upper == away.upper():
        odds_val = odds.get("away")
        implied_pct = (implied.get("away") or 0) * 100
    elif "DRAW" in selection_upper:
        odds_val = odds.get("draw")
        implied_pct = (implied.get("draw") or 0) * 100
    else:
        odds_val = odds.get("home")  # best-effort fallback for non-h2h markets
        implied_pct = (implied.get("home") or 0) * 100

    if not odds_val:
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": "Could not resolve odds for the model's selection — treated as no bet.",
            "research_warnings": research_warnings,
        }

    # Cap confidence at what the validated research actually supports.
    news_entry = match_news.get(match_meta["match"], {})
    ceiling = news_entry.get("confidence_ceiling", "LOW")
    model_confidence = (result.get("confidence") or "LOW").upper()
    confidence = model_confidence if CONFIDENCE_RANK.get(model_confidence, 0) <= CONFIDENCE_RANK.get(ceiling, 0) else ceiling

    evidence = Evidence(
        evidence_sufficient=bool(result.get("evidence_sufficient", False)),
        odds=float(odds_val),
        our_probability=float(result.get("our_probability", 0)),
        implied_probability=implied_pct,
        confidence=confidence,
        uncertainty_flags=result.get("uncertainty_flags", []),
    )
    verdict = classify(evidence)

    if verdict.risk == RISK_NO_BET:
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": sanitize_reasoning(result.get("reasoning", "")) or "; ".join(verdict.reasons),
            "research_warnings": research_warnings + [f"classifier: {r}" for r in verdict.reasons],
        }

    reasoning_sentence = _one_sentence(sanitize_reasoning(result.get("reasoning", "")))
    bet_type_reason = build_bet_type_reason(verdict.bet_type, reasoning_sentence)
    final_explanation = build_final_explanation(reasoning_sentence, verdict.risk, evidence.uncertainty_flags)

    # Validate before returning — if this ever fails, the caller must treat
    # the run as NO_BET rather than publish unsafe copy.
    for text in (bet_type_reason, final_explanation):
        validate_text(text, risk=verdict.risk, bet_type=verdict.bet_type, public=False)

    return {
        "has_pick": True,
        "match": match_meta["match"],
        "sport": match_meta["sport"],
        "sport_label": SPORT_LABELS.get(match_meta["sport"], match_meta["sport"]),
        "home_team": home,
        "away_team": away,
        "kickoff": match_meta["kickoff"],
        "selection": selection_upper,
        "market": result.get("market", "Head to Head"),
        "odds": f"{float(odds_val):.2f}",
        "our_probability": evidence.our_probability,
        "implied_probability": round(implied_pct, 1),
        "edge_pct": evidence.edge_pct,
        "risk": verdict.risk,
        "bet_type": verdict.bet_type,
        "bet_type_label": BET_TYPE_LABELS[verdict.bet_type],
        "bet_type_reason": bet_type_reason,
        "final_explanation": final_explanation,
        "confidence": confidence,
        "confidence_label": confidence,
        "uncertainty_flags": evidence.uncertainty_flags,
        "public_caution": RISK_PUBLIC_CAUTION.get(verdict.risk),
        "research_warnings": research_warnings,
        "big_game": match_meta.get("big_game", False),
    }
