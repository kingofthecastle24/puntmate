"""
generate_pick.py — selects ONE official PuntMate pick (or NO_BET) per run.

This replaces the old three-personality system (investor/punter/gambler each
producing their own pick). That design is what caused a real live-post bug:
three picks could land on the same match, the renderer silently overwrote
files when that happened, and — separately — one personality's own reasoning
text ("no pick meets my criteria... sitting this one out") was still posted
as if it were a live recommendation, because nothing checked the copy against
the classification before it went out.

Flow:
  1. Claude proposes EVERY genuinely defensible match+market it can find (0,
     1, or several candidates — no ranking, no tone, no verdict from Claude,
     just probability estimate, confidence, uncertainty flags per candidate).
     Phase 1: Claude can evaluate head-to-head, spreads (handicap) and totals
     (over/under) where available, and may draw on general knowledge of the
     teams/competition as supporting context — not just literal scraped news
     snippets — but may NOT invent specific, checkable facts (exact injuries,
     exact recent scores, roster news) that weren't given.
  2. pick_classifier.classify() deterministically decides RISK
     (STANDARD_PICK / RISKY_PICK / NO_BET) and BET_TYPE (INVESTOR_BET /
     PUNTER_BET / GAMBLER_BET / NO_BET) for EACH candidate from its evidence
     — Claude's own opinion of its confidence is capped by how much
     validated research actually backed it (see
     research_validator.assess_evidence_strength).
  3. Phase 2: if more than one candidate survives classification (i.e. is
     not NO_BET), the featured pick is chosen deterministically by bet-type
     preference — INVESTOR_BET > PUNTER_BET > GAMBLER_BET, ties broken by
     STANDARD_PICK over RISKY_PICK, then by edge_pct. This is a tie-break
     among genuinely defensible candidates, not a quota: if only a
     Gambler-tier candidate clears the bar today, that is what gets
     featured — nothing is upgraded or invented to fill an Investor slot.
  4. Copy (bet-type reason, final explanation, Telegram text, Instagram
     caption) is generated from fixed tone templates + a cleaned one-line
     excerpt of Claude's reasoning for the featured candidate only, then run
     through copy_validator before anything is accepted.

If nothing clears the bar, this returns a NO_BET result — never three
fallback picks, never a contradiction between the verdict and the copy.
"""

import anthropic
import json
import os
import re

from pick_classifier import Evidence, classify, RISK_NO_BET, RISK_STANDARD, BET_NO_BET
from copy_validator import validate_text, CopyValidationError, BANNED_TONE_PHRASES, STAKE_PHRASES
from text_format import truncate_at_sentence

SPORT_LABELS = {
    "soccer_fifa_world_cup": "FIFA World Cup 2026",
    "rugbyleague_nrl": "NRL",
    "rugbyunion_super_rugby": "Super Rugby",
    "rugbyunion_international": "Test Rugby",  # added 2026-07-18 dry-run: fetch_odds.py
    # gained this sport key the same day (commit 63fb7e4) but this dict was never
    # updated, so any real pick on a Test match would have shown "PUNTMATE NZ —
    # rugbyunion_international" (the raw API sport key) in the live Telegram/IG
    # copy instead of a readable label. Found via the weekend-multi dry run
    # (2026-07-18) against the real All Blacks v Ireland fixture -- see also
    # fetch_odds.py's SPORT_LABELS, which had the same gap.
    "mma_mixed_martial_arts": "UFC",
    "tennis_atp_wimbledon": "Wimbledon",
    "tennis_wta_wimbledon": "Wimbledon",
    "aussierules_afl": "AFL",
    "baseball_mlb": "MLB",
    "basketball_nba": "NBA",
    "soccer_epl": "Premier League",
    "cricket_international_t20": "T20 Cricket",
    "boxing_boxing": "Boxing",
    "icehockey_nhl": "NHL",
}

# TAB NZ runs rotating "multi insurance" promos grouped by sport category —
# e.g. "4+ Leg Multi on any AFL, Rugby Union, or Rugby League game: 1 leg
# fails, get up to $50 back" or "...on Men & Women Professional US
# Basketball, NHL and MLB". These rotate and the exact leg-count/refund
# amount changes, so this is NOT used to pick selections or change what
# clears the classifier's bar — it ONLY flags, informationally, whether the
# multi as genuinely constructed happens to sit entirely within one such
# category at 4+ legs, so Micah can check the live TAB/Betcha T&Cs and
# decide whether to mention it. Never forces a leg count or swaps a
# genuinely-clearing leg for a same-category one just to chase a promo.
TAB_MULTI_PROMO_CATEGORIES = {
    "rugby_codes": {"rugbyleague_nrl", "rugbyunion_super_rugby", "rugbyunion_international", "aussierules_afl"},
    "us_team_sports": {"baseball_mlb", "basketball_nba", "icehockey_nhl"},
    "football": {"soccer_fifa_world_cup", "soccer_epl"},
    "mma": {"mma_mixed_martial_arts"},
}
TAB_MULTI_PROMO_MIN_LEGS = 4  # the AFL/Rugby, US-sports and Football promos are all "4+ legs" as of 2026-07-18


def _tab_multi_promo_hint_from_sports(sport_keys):
    """Returns a short, internal-only string describing which TAB
    multi-insurance promo category this multi sits entirely within (if any,
    and if it meets that category's leg-count floor), else None. See the
    module comment on TAB_MULTI_PROMO_CATEGORIES above — this never
    influences which legs get selected."""
    if len(sport_keys) < TAB_MULTI_PROMO_MIN_LEGS:
        return None
    unique_sports = set(sport_keys)
    for category, sports_in_category in TAB_MULTI_PROMO_CATEGORIES.items():
        if unique_sports <= sports_in_category:
            return (
                f"All {len(sport_keys)} legs fall within TAB's '{category.replace('_', ' ')}' "
                f"multi-insurance category (4+ legs, e.g. bonus cash back if one leg fails) — "
                f"check the current live T&Cs/refund amount on tab.co.nz before mentioning this "
                f"publicly, these rotate."
            )
    return None

CONFIDENCE_RANK = {"LOW": 0, "MODERATE": 1, "HIGH": 2}

# Hard cap on fixtures shown to Claude in one prompt (see generate_pick_for_matches).
MAX_MATCHES_IN_PROMPT = 25

FOCUS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "focus_matches.txt")


def _load_focus_keywords():
    """Owner focus list (config/focus_matches.txt) — keywords, one per line,
    # comments allowed. Missing file = no focus."""
    try:
        with open(FOCUS_CONFIG_PATH) as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.strip().startswith("#")]
    except OSError:
        return []


def _is_focus_match(match_name, keywords):
    low = (match_name or "").lower()
    return any(k.lower() in low for k in keywords)

# Phase 2: featured-pick preference order when multiple genuinely defensible
# candidates exist on the same day. Lower number = preferred. This is only a
# tie-break among candidates that ALREADY cleared the classifier's bar on
# their own merits — it never changes what tier a candidate is classified
# into, and never manufactures a candidate that doesn't otherwise exist.
# Degenerate Multi bars (2026-07-19): the extreme-payout mega multi.
DEGENERATE_MIN_LEGS = 6
DEGENERATE_MIN_COMBINED_ODDS = 100.0

BET_TYPE_PRIORITY = {"INVESTOR_BET": 0, "PUNTER_BET": 1, "GAMBLER_BET": 2}
RISK_PRIORITY = {RISK_STANDARD: 0, "RISKY_PICK": 1}

SYSTEM_PROMPT = """You are PuntMate NZ — a mate who knows sport, not a financial analyst.
You talk like someone who actually watches the games and has a read on form, not
someone reading off a spreadsheet. Plain NZ English, honest about uncertainty,
never corporate or robotic.

You will be shown today's matches with bookmaker odds — head-to-head, and
where available, spreads (handicap) and totals (over/under) — plus any
validated recent news/form snippets. Your job is ONLY to assess the evidence
for EVERY match and market shown — you do NOT decide risk level or bet type,
that's calculated separately, and you do NOT rank or choose a "best" one —
a separate deterministic step does that after you're done.

You may draw on your general knowledge of these teams, players and this
competition as SUPPORTING CONTEXT — typical squad strength, recent
trajectory, historical patterns, home-ground advantage, style matchups —
alongside whatever odds and news you're given. This is legitimate: a real
tipster doesn't only work from a couple of scraped headlines.

But you must NEVER invent a specific, checkable fact that wasn't given to
you — no fabricated injuries, no made-up recent scores, no invented lineup
news. General knowledge of "this team is usually strong at home" is fine.
Claiming "their star fullback is out injured" when you weren't told that is
not — that's exactly the kind of fabrication that has caused real problems
before. If you're not sure whether something counts as general knowledge or
a specific fact you're inventing, treat it as the latter and leave it out.

Never mention stake sizes, units, dollar amounts to bet, or bankroll
percentages — that is not your job and must never appear in your reasoning.

Your "reasoning" must make a SPECIFIC, CONCRETE case for this exact
selection — name the actual teams/players and the actual factor doing the
work (a real form trend, a real head-to-head pattern, a specific piece of
validated news, a genuine squad-strength read for THESE two sides). Generic
genre filler that would apply to almost any match in this competition —
"mid-season games between finals hopefuls can be cagey", "derbies are never
straightforward", "anything can happen in a knockout game" — is not a reason
and must not be the main thrust of your case. If the only thing you can
say is generic, that's a sign the edge isn't real: lower your confidence or
leave the candidate out rather than dress up a generic observation as
specific analysis.

"uncertainty_flags" must ONLY be genuine punter-facing risk factors about the
MATCH or TEAMS — e.g. "star fullback is a late fitness doubt", "wet weather
forecast for kickoff", "opponent missing two regular starters". They must
NEVER be commentary about your own research process, sources, or note-taking
— never mention snippets, articles, sources, "copy-paste", "different week",
"beyond general knowledge", whether something is verified, or anything else
about where your information came from or how much you trust it. That kind
of doubt belongs in your confidence rating, not in a flag that gets shown to
real punters. (This is not hypothetical: a real live post once went out
reading "Worth knowing: Warriors news snippet references Cowboys not
Dragons — possible copy-paste from different week" — that sentence is about
your own source material, not about the match, and must never be written
into uncertainty_flags or reasoning again.) If your source material seems
mismatched or unreliable, just don't rely on it and say so honestly in
plain terms about your confidence — don't narrate the mismatch itself.

Critically: an uncertainty_flag must NEVER argue the opposite side of your
own selection. Don't back UNDER 3.5 in your reasoning and then flag "this
game could actually be high-scoring" — that's not a risk factor, that's
rebutting your own pick in public, and it reads as though you don't believe
what you just wrote. (Real example that shipped and shouldn't have: reasoning
argued France v England's third-place playoff would be cagey and low-scoring,
then the uncertainty_flag said "third-place playoffs can occasionally
produce high-scoring open games" — directly undercutting the pick right
after making it.) A genuine risk factor narrows HOW CONFIDENT you are without
contradicting WHICH SIDE you picked — e.g. "the under relies on both defenses
holding up; a red card or two could blow the total out" is fine because it's
about the mechanism, not a claim that the other side is just as likely. If
your only genuine caveat directly argues the other outcome, that means your
own confidence should be LOW (or the candidate should be left out) — don't
paper over that by stating the contradiction as a footnote.

Return ONLY valid JSON, no markdown, no extra text."""


def _format_market_lines(match):
    """Build the odds lines for one match, including spreads/totals when the
    match carries them (Phase 1 — previously head-to-head only)."""
    odds = match["odds"]
    implied = match.get("implied_probs", {}) or {}
    lines = [
        f"  Head-to-Head — Home ({match['home_team']}): {odds['home']} (implied {implied.get('home', 0)*100:.1f}%), "
        f"Away ({match['away_team']}): {odds['away']} (implied {implied.get('away', 0)*100:.1f}%)"
        + (f", Draw: {odds['draw']} (implied {implied.get('draw', 0)*100:.1f}%)" if odds.get("draw") else "")
    ]

    extra = match.get("markets_extra") or {}
    spread = extra.get("spreads")
    if spread:
        lines.append(
            f"  Spread/Handicap — {match['home_team']} {spread['home']['point']:+g} @ {spread['home']['price']}, "
            f"{match['away_team']} {spread['away']['point']:+g} @ {spread['away']['price']}"
        )
    total = extra.get("totals")
    if total:
        lines.append(
            f"  Total — Over {total['over']['point']} @ {total['over']['price']}, "
            f"Under {total['under']['point']} @ {total['under']['price']}"
        )
    return "\n".join(lines)


def _build_prompt(matches, match_news):
    blocks = []
    for i, match in enumerate(matches, 1):
        news = match_news.get(match["match"], {})
        news_text = news.get("text", "")
        news_block = f"\n  Validated news/form:\n{news_text}" if news_text else "\n  Validated news/form: none found — general knowledge context is fine if you have a genuine basis, but say so honestly if you don't"

        blocks.append(
            f"Match {i}: {match['match']}\n"
            f"  Sport: {SPORT_LABELS.get(match['sport'], match['sport'])} | Kickoff: {match['kickoff']}\n"
            f"{_format_market_lines(match)}{news_block}"
        )
    matches_text = "\n\n".join(blocks)

    return f"""Today's matches:

{matches_text}

Assess every match across every market shown (head-to-head, and spread/total
where listed). List EVERY selection that has a genuinely defensible edge (the
evidence actually supports it beating the bookmaker's implied probability) —
there may be zero, one, or several across today's matches. Don't rank them
and don't try to pick a "best" one — just report each one honestly on its
own merits, including ones you'd only call a longshot swing. A separate
deterministic step decides which one gets featured. Do NOT stretch a
marginal case just to lengthen the list — only include ones you'd genuinely
defend.

Return this exact JSON:
{{
  "candidates": [
    {{
      "match": "exact match name from above",
      "sport": "sport key matching the match",
      "market_type": "h2h, spread, or total",
      "selection": "TEAM NAME / DRAW for h2h; TEAM NAME for spread; Over or Under for total",
      "line": null for h2h, or the handicap/total number for spread/total (e.g. -6.5 or 42.5),
      "market": "Head to Head, Handicap, or Total — human-readable label",
      "our_probability": 58,
      "evidence_sufficient": true,
      "confidence": "HIGH or MODERATE or LOW — how strong is the evidence you actually have (validated news AND/OR genuine general knowledge), not how you feel about the team",
      "uncertainty_flags": ["short phrase", "short phrase"],
      "reasoning": "2-3 sentences, plain NZ English, mate-to-mate tone"
    }}
  ],
  "reasoning": "1-2 sentences on today overall — only used if candidates is empty"
}}

If nothing today is defensible, return "candidates": [] with the top-level
"reasoning" explaining why."""


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


def _one_sentence(text, max_len=400):
    """Reduce model reasoning down to its first complete sentence(s) for use
    in public copy. max_len is a safety net against a pathological run-on
    from the model, not a real Telegram/Instagram constraint (both platforms
    allow far more than this) — see text_format.truncate_at_sentence for why
    a fixed 160-char slice used to cut posts off mid-sentence.
    """
    return truncate_at_sentence(text, max_len)


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


def build_final_explanation(reasoning_sentence, risk, uncertainty_flags, research_warnings=None):
    """Builds the public final_explanation. uncertainty_flags are NEVER
    appended to public copy any more — see below for why — they're always
    diverted to research_warnings (internal-only, visible in the Gmail
    preview / post-metadata.json) instead.

    INCIDENT #1 (2026-07-17): this used to join uncertainty_flags into
    public copy unconditionally, trusting the system prompt alone to keep
    the model from writing anything internal-sounding into that field. It
    didn't — "Worth knowing: Warriors news snippet references Cowboys not
    Dragons — possible copy-paste from different week" shipped live. Fixed
    at the time with copy_validator.check_internal_leak filtering each flag
    before it was allowed into the public "Worth knowing:" line.

    INCIDENT #2 (2026-07-19, real dry run, Spain v Argentina): the
    check_internal_leak filter worked (nothing about sources/snippets
    leaked), but a DIFFERENT problem in the same mechanism showed up: the
    reasoning backed UNDER 2.5 arguing the game would be tight and
    low-scoring, then the "Worth knowing" flag said the final "can produce
    nervy, open-ended attacks" and Argentina's attack is "capable of
    blowing games open" — directly arguing the OPPOSITE of the pick, in
    public, right after making the case for it. A 2026-07-19 prompt change
    explicitly told the model never to do this — the very next real test
    still did it. Prompting alone is not reliable enough for this, the same
    lesson as incident #1: a fixed instruction can't be trusted to hold on
    every generation, only a code-level rule can guarantee it.

    Rather than attempt a fragile "does this flag contradict the pick"
    detector (a much harder, much more error-prone NLU problem than
    detecting self-referential source commentary), the reliable fix is
    structural: uncertainty_flags are genuinely useful for Micah's own
    review, but not worth the reputational risk of ever again shipping
    copy that argues both sides of its own pick in public. They now always
    go to research_warnings instead of the public post, full stop.
    """
    if uncertainty_flags and research_warnings is not None:
        for flag in uncertainty_flags:
            research_warnings.append(f"uncertainty_flag (internal only, not shown publicly): {flag!r}")
    return reasoning_sentence.strip()


def _resolve_selection_odds(match_meta, market_type, selection, line):
    """Resolve (odds_val, implied_pct) for a candidate's chosen selection,
    across h2h, spread and total markets. Returns (None, None) if it can't
    be resolved (unknown market/selection/missing line data) — the caller
    drops that candidate rather than guessing."""
    home = match_meta["home_team"]
    away = match_meta["away_team"]
    selection_upper = (selection or "").upper()

    if market_type == "h2h" or not market_type:
        odds = match_meta["odds"]
        implied = match_meta.get("implied_probs", {}) or {}
        if selection_upper == home.upper():
            return odds.get("home"), (implied.get("home") or 0) * 100
        if selection_upper == away.upper():
            return odds.get("away"), (implied.get("away") or 0) * 100
        if "DRAW" in selection_upper:
            return odds.get("draw"), (implied.get("draw") or 0) * 100
        return None, None

    extra = match_meta.get("markets_extra") or {}

    if market_type == "spread":
        spread = extra.get("spreads")
        if not spread or line is None:
            return None, None
        from fetch_odds import calc_two_way_implied_probs
        if selection_upper == home.upper() and abs(spread["home"]["point"] - float(line)) < 0.01:
            probs = calc_two_way_implied_probs(spread["home"]["price"], spread["away"]["price"])
            return spread["home"]["price"], (probs["a"] * 100) if probs else None
        if selection_upper == away.upper() and abs(spread["away"]["point"] - float(line)) < 0.01:
            probs = calc_two_way_implied_probs(spread["home"]["price"], spread["away"]["price"])
            return spread["away"]["price"], (probs["b"] * 100) if probs else None
        return None, None

    if market_type == "total":
        total = extra.get("totals")
        if not total or line is None:
            return None, None
        from fetch_odds import calc_two_way_implied_probs
        if "OVER" in selection_upper and abs(total["over"]["point"] - float(line)) < 0.01:
            probs = calc_two_way_implied_probs(total["over"]["price"], total["under"]["price"])
            return total["over"]["price"], (probs["a"] * 100) if probs else None
        if "UNDER" in selection_upper and abs(total["under"]["point"] - float(line)) < 0.01:
            probs = calc_two_way_implied_probs(total["over"]["price"], total["under"]["price"])
            return total["under"]["price"], (probs["b"] * 100) if probs else None
        return None, None

    return None, None


def _display_selection(market_type, selection, line):
    """How the selection should read publicly, e.g. 'WARRIORS -6.5' or 'OVER 42.5'."""
    selection_upper = (selection or "").upper()
    if market_type in ("spread", "total") and line is not None:
        try:
            return f"{selection_upper} {float(line):+g}" if market_type == "spread" else f"{selection_upper} {float(line):g}"
        except (TypeError, ValueError):
            return selection_upper
    return selection_upper


def _classify_candidate(raw, matches, match_news, warnings):
    """Resolve + deterministically classify a single raw candidate dict from
    the model. Returns None (and appends an explanatory warning) if the
    candidate can't be trusted or classified; otherwise returns a dict
    bundling the classified verdict with everything needed to build the
    final pick if this candidate ends up featured."""
    match_meta = next((m for m in matches if m["match"] == raw.get("match")), None)
    if not match_meta:
        warnings.append(f"model hallucinated a match not in the candidate list: {raw.get('match')!r}")
        return None

    market_type = (raw.get("market_type") or "h2h").strip().lower()
    if market_type not in ("h2h", "spread", "total"):
        market_type = "h2h"
    line = raw.get("line")
    odds_val, implied_pct = _resolve_selection_odds(match_meta, market_type, raw.get("selection"), line)

    if not odds_val or implied_pct is None:
        warnings.append(f"[{raw.get('match')}] could not resolve odds for candidate selection/market/line — dropped")
        return None

    news_entry = match_news.get(match_meta["match"], {})
    ceiling = news_entry.get("confidence_ceiling", "MODERATE")
    model_confidence = (raw.get("confidence") or "LOW").upper()
    confidence = model_confidence if CONFIDENCE_RANK.get(model_confidence, 0) <= CONFIDENCE_RANK.get(ceiling, 0) else ceiling

    evidence = Evidence(
        evidence_sufficient=bool(raw.get("evidence_sufficient", False)),
        odds=float(odds_val),
        our_probability=float(raw.get("our_probability", 0)),
        implied_probability=implied_pct,
        confidence=confidence,
        uncertainty_flags=raw.get("uncertainty_flags", []),
    )
    verdict = classify(evidence)

    return {
        "raw": raw,
        "match_meta": match_meta,
        "market_type": market_type,
        "line": line,
        "odds_val": odds_val,
        "confidence": confidence,
        "evidence": evidence,
        "verdict": verdict,
    }


# 2026-07-18 (Micah): cater to a NZ/Australian audience -- prioritise
# whatever generates the most buzz there day to day: the FIFA World Cup,
# NRL, both rugby codes (Super Rugby + Test matches), and MMA/UFC -- ahead
# of everything else. "Dive into other sports" (MLB, AFL, cricket, boxing,
# etc.) only when nothing genuine clears the bar in these first -- MLB
# etc. are acceptable fallback content, not excluded, just not the first
# port of call. Same mechanism as owner-focus fixtures: this is a
# PREFERENCE among candidates that already independently cleared the
# classifier's bar on their own merits -- it can never promote a NO_BET
# candidate or invent a priority-sport pick that isn't genuinely there. On
# a day with only a defensible MLB candidate and nothing in the priority
# sports, the MLB pick still runs -- "then dive into other sports" means
# exactly that, not "never".
PRIORITY_SPORTS = {
    "soccer_fifa_world_cup", "rugbyleague_nrl", "rugbyunion_super_rugby",
    "rugbyunion_international", "mma_mixed_martial_arts",
}


def _select_featured(classified, focus_keywords=None):
    """Phase 2: among candidates that actually cleared the classifier's bar
    (risk != NO_BET), pick the one to feature this run. Ordering, strongest
    signal first: (1) owner-focus fixtures (config/focus_matches.txt), (2)
    priority sports NZ punters actually bet on (NRL/Rugby/MMA — see
    PRIORITY_SPORTS), (3) INVESTOR_BET > PUNTER_BET > GAMBLER_BET, (4)
    STANDARD_PICK over RISKY_PICK, (5) higher edge. This never reclassifies
    or upgrades a candidate; it only orders candidates that already
    independently earned their tier — focus or priority-sport can promote a
    genuine Gambler-tier candidate over a non-focus/non-priority Investor
    one (that's the owner's editorial call), but neither can ever conjure a
    candidate that didn't clear the bar."""
    eligible = [c for c in classified if c["verdict"].risk != RISK_NO_BET]
    if not eligible:
        return None
    focus_keywords = focus_keywords or []
    eligible.sort(
        key=lambda c: (
            0 if _is_focus_match(c["match_meta"].get("match", ""), focus_keywords) else 1,
            0 if c["match_meta"].get("sport") in PRIORITY_SPORTS else 1,
            BET_TYPE_PRIORITY.get(c["verdict"].bet_type, 99),
            RISK_PRIORITY.get(c["verdict"].risk, 99),
            -c["evidence"].edge_pct,
        )
    )
    return eligible[0]


def generate_pick_for_matches(matches, match_news, build_multis=False):
    """
    matches: list of match dicts from fetch_odds.fetch_upcoming_odds()
    match_news: dict {match_name: fetch_news() result dict}

    Returns a single pick dict with keys:
      has_pick, match, sport, sport_label, home_team, away_team, kickoff,
      selection, market, odds, our_probability, implied_probability, edge_pct,
      risk, bet_type, bet_type_reason, final_explanation, confidence,
      confidence_label, uncertainty_flags, research_warnings
    or {"has_pick": False, "reasoning": "..."} when nothing clears the bar.

    Phase 2: when multiple candidates clear the bar on the same day, the
    featured one is chosen by bet-type preference (Investor > Punter >
    Gambler) — see _select_featured.

    build_multis (2026-07-19, Micah): the two multi tiers (Punter /
    Gambler-Degenerate) are now OFF by default. The ordinary daily run never
    builds them at all — Micah didn't want the Gambler/Degenerate multi
    (or, per his "review the whole weekend" point, either tier) firing off
    the back of just one day's fixtures; multis are now exclusively a
    weekend-pool feature (see generate_weekend_multi.py), which passes
    build_multis=True with a wider multi-day match list so the tiers are
    assembled from the WHOLE weekend, not a single day. When False,
    punter_multi_legs/gambler_multi_legs are always [] and their promo hints
    are always None — build_review_package.py's _freeze_multi_tier already
    no-ops on an empty list, so this alone guarantees no multi content ever
    reaches a daily post.
    """
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    research_warnings = []
    for m in matches:
        research_warnings += match_news.get(m["match"], {}).get("warnings", [])

    # Widened coverage (2026-07-18) can put 50+ fixtures in front of Claude on
    # a busy day. Cap what goes in the prompt: SPORTS is already in NZ-audience
    # priority order and fetch_upcoming_odds() returns matches in that order,
    # so keeping the first N preserves the intended priority. Without this, a
    # big slate both bloats the prompt and invites a long candidates array.
    # Owner focus list: focus fixtures are hoisted to the front so the prompt
    # cap can never drop them, and they're flagged to the model below. Focus
    # biases ATTENTION and tie-breaks — never verdicts (a focus game with no
    # genuine edge is still no bet on that game).
    focus_keywords = _load_focus_keywords()
    if focus_keywords:
        matches = sorted(matches, key=lambda m: 0 if _is_focus_match(m.get("match", ""), focus_keywords) else 1)
    if len(matches) > MAX_MATCHES_IN_PROMPT:
        research_warnings.append(
            f"{len(matches)} fixtures available today — only the first {MAX_MATCHES_IN_PROMPT} "
            f"(owner-focus fixtures first, then sport priority) were assessed"
        )
        matches = matches[:MAX_MATCHES_IN_PROMPT]

    prompt = _build_prompt(matches, match_news)
    if focus_keywords:
        focused = [m["match"] for m in matches if _is_focus_match(m.get("match", ""), focus_keywords)]
        if focused:
            prompt += (
                "\n\nOWNER FOCUS: give particular attention to assessing these fixtures: "
                + "; ".join(focused)
                + ". Same evidence standards apply — if there is no genuine edge in a focus "
                "fixture, say so honestly rather than stretching to produce a candidate for it."
            )
    message = client.messages.create(
        model="claude-sonnet-4-6",
        # 1500 was enough for the original 1-6 fixture slate but a widened
        # slate can produce a long candidates array; run #49 (2026-07-17,
        # 59 fixtures) hit the cap and the truncated JSON crashed the run.
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw_text = message.content[0].text
    try:
        result = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        # FAIL-SAFE (added after run #49 crashed here): an unparseable model
        # response must degrade to an honest NO_BET, never crash the run.
        # Most likely cause is output truncation (check stop_reason).
        stop_reason = getattr(message, "stop_reason", None)
        research_warnings.append(
            f"model response could not be parsed as JSON ({e}; stop_reason={stop_reason}) — "
            f"failing safe to NO_BET rather than guessing"
        )
        print(f"::warning::generate_pick: unparseable model JSON ({e}; stop_reason={stop_reason}) — NO_BET fail-safe")
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": "Couldn't complete today's assessment cleanly — no pick rather than a rushed one.",
            "research_warnings": research_warnings,
        }

    raw_candidates = result.get("candidates") or []
    if not raw_candidates:
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": result.get("reasoning", "Nothing today clears the bar for a defensible pick."),
            "research_warnings": research_warnings,
        }

    classify_warnings = []
    classified = []
    for raw in raw_candidates:
        c = _classify_candidate(raw, matches, match_news, classify_warnings)
        if c is not None:
            classified.append(c)
    research_warnings += classify_warnings

    if not classified:
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": "None of the model's proposed candidates could be resolved to real odds — treated as no bet.",
            "research_warnings": research_warnings,
        }

    for c in classified:
        if c["verdict"].risk == RISK_NO_BET:
            research_warnings += [f"classifier [{c['match_meta']['match']} / {c['market_type']}]: {r}" for r in c["verdict"].reasons]

    featured = _select_featured(classified, focus_keywords)

    if featured is None:
        # Every candidate the model proposed was independently classified as
        # NO_BET on its own merits (thin edge, insufficient evidence, etc).
        best_reasoning = sanitize_reasoning(classified[0]["raw"].get("reasoning", ""))
        return {
            "has_pick": False,
            "risk": RISK_NO_BET,
            "bet_type": BET_NO_BET,
            "reasoning": best_reasoning or "No candidate cleared the bar for a defensible pick today.",
            "research_warnings": research_warnings,
        }

    match_meta = featured["match_meta"]
    market_type = featured["market_type"]
    line = featured["line"]
    odds_val = featured["odds_val"]
    confidence = featured["confidence"]
    evidence = featured["evidence"]
    verdict = featured["verdict"]
    raw = featured["raw"]

    reasoning_sentence = _one_sentence(sanitize_reasoning(raw.get("reasoning", "")))
    bet_type_reason = build_bet_type_reason(verdict.bet_type, reasoning_sentence)
    final_explanation = build_final_explanation(reasoning_sentence, verdict.risk, evidence.uncertainty_flags, research_warnings)

    # Validate before returning — if this ever fails, the caller must treat
    # the run as NO_BET rather than publish unsafe copy. public=True because
    # bet_type_reason/final_explanation ARE what becomes the public Telegram/
    # Instagram copy (see build_review_package.py) — there is no reason for
    # this check to be more lenient than the real one it's standing in for.
    for text in (bet_type_reason, final_explanation):
        validate_text(text, risk=verdict.risk, bet_type=verdict.bet_type, public=True)

    selection_display = _display_selection(market_type, raw.get("selection"), line)
    market_label = raw.get("market") or {"h2h": "Head to Head", "spread": "Handicap", "total": "Total"}[market_type]

    other_defensible = len(classified) - 1

    # Phase 5/6 (2026-07-19, Micah): the multi is now TWO independent,
    # always-optional tiers instead of one blended list, so followers can
    # pick their own risk appetite:
    #   - Punter Multi: INVESTOR_BET/PUNTER_BET legs — the measured side.
    #   - Gambler/Degenerate Multi: GAMBLER_BET legs — the "shooting your
    #     shot" side, framed as a small-stake swing (see build_multi_text /
    #     the Multi.dc.html card, which show an illustrative stake->return
    #     figure computed purely from combined odds — never a promise).
    # Same ground rules as before, per tier: every leg already independently
    # cleared pick_classifier's bar on its own merits — nothing is padded or
    # forced. Each tier needs its own 3+ legs on distinct matches to fire at
    # all; there is no ceiling within a tier; the two tiers can't share a
    # match (a candidate's bet_type puts it in exactly one tier).
    PUNTER_MULTI_BET_TYPES = {"INVESTOR_BET", "PUNTER_BET"}
    GAMBLER_MULTI_BET_TYPES = {"GAMBLER_BET"}
    ALL_MULTI_BET_TYPES = PUNTER_MULTI_BET_TYPES | GAMBLER_MULTI_BET_TYPES

    def _assemble_multi_tier(allowed_bet_types):
        legs, leg_sports, seen_matches = [], [], set()
        for c in sorted(
            (c for c in classified
             if c["verdict"].risk != RISK_NO_BET and c["verdict"].bet_type in allowed_bet_types),
            key=lambda c: (
                BET_TYPE_PRIORITY.get(c["verdict"].bet_type, 9),
                RISK_PRIORITY.get(c["verdict"].risk, 9),
                -c["evidence"].edge_pct,
            ),
        ):
            m = c["match_meta"]["match"]
            if m in seen_matches:
                continue
            seen_matches.add(m)
            legs.append({
                "match": m,
                "sport_label": SPORT_LABELS.get(c["match_meta"]["sport"], c["match_meta"]["sport"]),
                "selection": _display_selection(c["market_type"], c["raw"].get("selection"), c["line"]),
                "market": c["raw"].get("market") or {"h2h": "Head to Head", "spread": "Handicap", "total": "Total"}[c["market_type"]],
                "odds": f"{float(c['odds_val']):.2f}",
            })
            leg_sports.append(c["match_meta"]["sport"])
        if len(legs) < 3:
            return [], []  # fewer than 3 genuine legs in this tier -> no multi today
        return legs, leg_sports

    if build_multis:
        punter_multi_legs, punter_multi_sports = _assemble_multi_tier(PUNTER_MULTI_BET_TYPES)
        gambler_multi_legs, gambler_multi_sports = _assemble_multi_tier(GAMBLER_MULTI_BET_TYPES)
        punter_multi_promo_hint = _tab_multi_promo_hint_from_sports(punter_multi_sports) if punter_multi_legs else None
        gambler_multi_promo_hint = _tab_multi_promo_hint_from_sports(gambler_multi_sports) if gambler_multi_legs else None

        # THE DEGENERATE MULTI (2026-07-19, Micah): "The Degenerate should be
        # like when there is a large number of bets and the multi needs to pay
        # off... extreme payoff... the least used item really." Definition:
        # pool EVERY genuine leg across ALL tiers into one mega multi, and
        # only call it a Degenerate when BOTH bars clear:
        #   - at least DEGENERATE_MIN_LEGS legs (a big slate of independent
        #     value, not a normal 3-4 leg day), AND
        #   - combined odds of at least DEGENERATE_MIN_COMBINED_ODDS (a
        #     genuinely extreme payout — $5 returns $500+).
        # Rare by construction: it needs an unusually deep weekend of
        # qualifying picks. When it fires it REPLACES the Gambler Multi that
        # weekend (the gambler legs are inside it, and two longshot products
        # side by side would dilute both) — the Punter Multi still posts.
        degenerate_multi_legs, degenerate_multi_sports = _assemble_multi_tier(ALL_MULTI_BET_TYPES)
        if degenerate_multi_legs:
            combined = 1.0
            for leg in degenerate_multi_legs:
                combined *= float(leg["odds"])
            if len(degenerate_multi_legs) < DEGENERATE_MIN_LEGS or combined < DEGENERATE_MIN_COMBINED_ODDS:
                degenerate_multi_legs, degenerate_multi_sports = [], []
        degenerate_multi_promo_hint = _tab_multi_promo_hint_from_sports(degenerate_multi_sports) if degenerate_multi_legs else None
        if degenerate_multi_legs:
            gambler_multi_legs, gambler_multi_promo_hint = [], None
    else:
        # Daily runs never build multis at all (see build_multis note above).
        punter_multi_legs, gambler_multi_legs, degenerate_multi_legs = [], [], []
        punter_multi_promo_hint, gambler_multi_promo_hint, degenerate_multi_promo_hint = None, None, None

    return {
        "has_pick": True,
        "match": match_meta["match"],
        "sport": match_meta["sport"],
        "sport_label": SPORT_LABELS.get(match_meta["sport"], match_meta["sport"]),
        "home_team": match_meta["home_team"],
        "away_team": match_meta["away_team"],
        "kickoff": match_meta["kickoff"],
        "market_type": market_type,
        "line": line,
        "selection": selection_display,
        "market": market_label,
        "odds": f"{float(odds_val):.2f}",
        "our_probability": evidence.our_probability,
        "implied_probability": round(evidence.implied_probability, 1),
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
        "other_defensible_candidates": other_defensible,
        "punter_multi_legs": punter_multi_legs,
        "punter_multi_promo_hint": punter_multi_promo_hint,  # internal only -- never surfaced in public copy
        "gambler_multi_legs": gambler_multi_legs,
        "gambler_multi_promo_hint": gambler_multi_promo_hint,
        "degenerate_multi_legs": degenerate_multi_legs,
        "degenerate_multi_promo_hint": degenerate_multi_promo_hint,  # internal only -- never surfaced in public copy
    }
