"""
copy_validator.py — deterministic (non-LLM) checks that block contradictory,
staking-related, or off-tone copy from ever reaching a public post.

This runs AFTER the pick has been classified and the copy has been drafted,
and BEFORE anything is frozen for review. If it fails, the pipeline must not
proceed to render/publish that copy — this is what would have caught the
France/Spain contradiction (NO_BET-only wording sitting inside a post that
was actually presented as a live pick).
"""

import re

# ---------------------------------------------------------------------------
# Banned phrases — corporate / financial-analyst tone. PuntMate talks like a
# mate who knows the sport, not an investment memo.
# ---------------------------------------------------------------------------
BANNED_TONE_PHRASES = [
    "capital allocation",
    "material volatility",
    "probability differential",
    "market inefficiency",
    "risk-adjusted return",
    "portfolio",
    "asset allocation",
    "expected value optimization",
    "alpha generation",
    "diversify your positions",
    "hedge your position",
    "quantitative model indicates",
    "our proprietary algorithm",
]

# ---------------------------------------------------------------------------
# Staking / unit / dollar-amount language — banned everywhere, on every
# platform, for every bet type. PuntMate never tells anyone how much to bet.
# ---------------------------------------------------------------------------
STAKE_PHRASES = [
    "units", "unit stake", "stake size", "suggested stake", "bet size",
    "% of bankroll", "percent of bankroll", "bankroll", "1u", "2u", "3u",
    "put $", "wager $", "risk $",
]
# Dollar amounts and explicit percentages presented as a stake, e.g. "$20 on this"
# or "bet 5%". Odds themselves (e.g. "$3.00" as a price, or "2.10") are fine —
# we only flag amounts adjacent to staking verbs, handled via STAKE_PHRASES
# above, plus this pattern for bare "X% of your bankroll"-style constructs.
STAKE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*%\s*(of\s+(your\s+)?bankroll|stake)\b", re.IGNORECASE)

# ---------------------------------------------------------------------------
# NO_BET-only phrases. These describe walking away from a match entirely —
# they must never appear alongside an actual selection (STANDARD_PICK or
# RISKY_PICK). This is exactly the bug that shipped live: "no pick meets my
# criteria... sitting this one out" sitting inside a post that still named
# France @ 2.50 as the pick.
# ---------------------------------------------------------------------------
NO_BET_ONLY_PHRASES = [
    "no pick meets my criteria",
    "no pick meets our criteria",
    "sitting this one out",
    "sit this one out",
    "no bet today",
    "nothing worth backing",
    "staying on the sidelines",
    "passing on this one",
]

# Internal research/debug language that must never leak into a PUBLIC post
# (Telegram message text or Instagram caption). It's fine in Gmail/Dispatch/
# metadata — those are internal review surfaces.
#
# INCIDENT (2026-07-17): a real live Telegram post shipped with "Worth
# knowing: Warriors news snippet references Cowboys not Dragons — possible
# copy-paste from different week; Dragons form unknown beyond general
# knowledge." This is Claude's own self-referential commentary about the
# quality/provenance of ITS OWN research inputs, written into the
# model-generated "uncertainty_flags" field (intended for genuine
# punter-facing risk caveats like "star player is a doubt") and then
# surfaced verbatim under a "Worth knowing:" prefix. The literal phrase list
# below didn't contain anything resembling that wording, so it sailed
# through check_internal_leak() uncaught. Fixed two ways: (1) this list is
# now much broader, and (2) INTERNAL_LEAK_PATTERNS below adds regex
# heuristics for the general CLASS of "commentary about my own sources"
# language, since a fixed phrase list can never fully anticipate a
# generative model's phrasing. See generate_pick.py's build_final_explanation
# for the matching upstream fix (each uncertainty_flag is now run through
# check_internal_leak individually before it's allowed into public copy).
INTERNAL_ONLY_PHRASES = [
    "research warning",
    "source_relevance",
    "confidence reduced due to",
    "evidence_sufficient",
    "validator rejected",
    "irrelevant sport",
    "rejected source",
    "no relevance to fixture",
    "validated source",
    "confidence capped",
    "team-name-only match",
    "no sport context",
    "news snippet",
    "news article",
    "copy-paste",
    "copy paste",
    "copied from",
    "different week",
    "beyond general knowledge",
    "form unknown",
    "unknown beyond",
    "could not verify",
    "couldn't verify",
    "cannot verify",
    "can't verify",
    "unable to verify",
    "no information found",
    "not enough information",
    "insufficient information",
    "data quality",
    "unreliable source",
    "mismatched source",
    "wrong fixture",
    "wrong match",
    "wrong team",
    "possible mix-up",
    "possible mixup",
    "may not be accurate",
    "unclear if this refers",
    "not sure if this is about",
    "general knowledge only",
    "general knowledge basis",
]

# Regex heuristics for self-referential commentary about the model's OWN
# research process or source material — phrased in ways a fixed phrase list
# can't fully anticipate. Deliberately broad: a false positive here just
# means a legitimate caveat gets rejected and suppressed from public copy
# (fail-closed, the correct behaviour), whereas a false negative means an
# internal QA note reaches real subscribers, which is what happened on
# 2026-07-17 and must not happen again.
INTERNAL_LEAK_PATTERNS = [
    re.compile(r"\bnews\s+(snippet|article|report|source)s?\b", re.IGNORECASE),
    re.compile(r"\breferences?\s+\w[\w\s]*?\bnot\b\s+\w+", re.IGNORECASE),  # "references Cowboys not Dragons"
    re.compile(r"\b(source|snippet|article)s?\s+(may|might|could)\s+(be|not)\b", re.IGNORECASE),
    re.compile(r"\bpossible\s+(copy[\s-]?paste|mix[\s-]?up|mismatch)\b", re.IGNORECASE),
]

# Responsible-gambling: GAMBLER_BET copy must never chase, promise, or imply
# guaranteed/all-in behaviour.
RG_BANNED_FOR_GAMBLER = [
    "guaranteed win", "guaranteed winner", "can't lose", "sure thing",
    "all in", "go big or go home", "chase", "bet it all", "lock of the day",
    "free money",
]


class CopyValidationError(ValueError):
    def __init__(self, violations):
        self.violations = violations
        super().__init__("; ".join(violations))


def _contains_any(text, phrases):
    low = text.lower()
    return [p for p in phrases if p.lower() in low]


def check_tone(text):
    return [f"banned corporate/analyst phrase: '{p}'" for p in _contains_any(text, BANNED_TONE_PHRASES)]


def check_staking_language(text):
    violations = [f"staking language: '{p}'" for p in _contains_any(text, STAKE_PHRASES)]
    if STAKE_PATTERN.search(text):
        violations.append("staking language: bankroll/stake percentage pattern")
    return violations


def check_no_bet_contradiction(text, risk):
    """NO_BET-only phrases must never appear on a real pick."""
    if risk in ("STANDARD_PICK", "RISKY_PICK"):
        hits = _contains_any(text, NO_BET_ONLY_PHRASES)
        return [f"NO_BET-only phrase on a {risk}: '{p}'" for p in hits]
    return []

def check_no_bet_has_no_selection(post_metadata):
    """A NO_BET post must not carry a pick, odds, or staking language."""
    violations = []
    if post_metadata.get("classification") == "NO_BET" or post_metadata.get("risk") == "NO_BET":
        if post_metadata.get("selection"):
            violations.append("NO_BET post must not include a 'selection' field")
        if post_metadata.get("odds"):
            violations.append("NO_BET post must not include an 'odds' field")
    return violations


def check_internal_leak(public_text):
    hits = _contains_any(public_text, INTERNAL_ONLY_PHRASES)
    violations = [f"internal/debug phrase leaked into public copy: '{p}'" for p in hits]
    for pattern in INTERNAL_LEAK_PATTERNS:
        match = pattern.search(public_text)
        if match:
            violations.append(f"internal/debug phrasing pattern leaked into public copy: '{match.group(0)}'")
    return violations


def check_gambler_rg(text, bet_type):
    if bet_type != "GAMBLER_BET":
        return []
    hits = _contains_any(text, RG_BANNED_FOR_GAMBLER)
    return [f"responsible-gambling violation for GAMBLER_BET: '{p}'" for p in hits]


def check_single_pick(post_metadata):
    """Guard against multiple picks / multiple bet types being expressed in
    one post — the pipeline must always settle on exactly one."""
    violations = []
    picks = post_metadata.get("picks")
    if isinstance(picks, list) and len(picks) > 1:
        violations.append(f"multiple picks present ({len(picks)}) — only one official pick is allowed")
    bet_types = post_metadata.get("bet_types")
    if isinstance(bet_types, list) and len(bet_types) > 1:
        violations.append(f"multiple bet types present ({bet_types}) — only one bet type is allowed")
    return violations


def validate_text(text, risk=None, bet_type=None, public=True):
    """Validate a single piece of copy (Telegram message, IG caption, etc).
    Raises CopyValidationError if anything is wrong."""
    violations = []
    violations += check_tone(text)
    violations += check_staking_language(text)
    if risk:
        violations += check_no_bet_contradiction(text, risk)
    if bet_type:
        violations += check_gambler_rg(text, bet_type)
    if public:
        violations += check_internal_leak(text)
    if violations:
        raise CopyValidationError(violations)
    return text


def validate_post(post_metadata, telegram_text, instagram_caption):
    """Full pre-freeze validation across the whole post. Raises
    CopyValidationError listing every violation found (not just the first)."""
    violations = []
    risk = post_metadata.get("risk") or post_metadata.get("classification")
    bet_type = post_metadata.get("bet_type")

    violations += check_single_pick(post_metadata)
    violations += check_no_bet_has_no_selection(post_metadata)

    for label, text in (("telegram", telegram_text), ("instagram", instagram_caption)):
        if not text:
            continue
        try:
            validate_text(text, risk=risk, bet_type=bet_type, public=True)
        except CopyValidationError as e:
            violations += [f"[{label}] {v}" for v in e.violations]

    if violations:
        raise CopyValidationError(violations)
    return True
