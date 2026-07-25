"""
pick_classifier.py — deterministic risk + bet-type classification.

This module never talks to an LLM. It takes the *evidence* an LLM (or a human)
has already extracted for a single candidate pick — probabilities, odds,
whether the evidence was actually sufficient, and any uncertainty flags — and
applies fixed, testable rules to decide two INDEPENDENT things:

  1. RISK classification  — how defensible/certain is this selection?
       STANDARD_PICK | RISKY_PICK
     (2026-07-25, Micah: NO_BET is no longer a pick classification. A real
     candidate is always STANDARD_PICK or RISKY_PICK. Whether a candidate is
     worth featuring at all is a separate question answered by is_backable();
     a day is only skipped when NO candidate is backable — i.e. fixtures,
     odds or reliable data are genuinely unavailable.)
  2. BET-TYPE classification — what flavour of bet is this (tone/style), not
     how risky it is.
       INVESTOR_BET | PUNTER_BET | GAMBLER_BET | NO_BET

Bet-type and risk are combined freely — e.g. GAMBLER_BET can be a
STANDARD_PICK (a longshot the evidence genuinely supports) or a RISKY_PICK
(the more typical case). INVESTOR_BET can be RISKY_PICK if the short-priced
favourite's evidence is thin. There is no fixed pairing.

Being outside the "preferred" odds range for a bet type does NOT by itself
force NO_BET — odds only ever push a pick toward RISKY_PICK or toward a
different bet-type bucket. Only insufficient evidence or an edge below the
minimum threshold produces NO_BET.

Phase 3: below the standard edge bar there is now a second, lower floor
(RISKY_MIN_EDGE_PCT). An edge that clears the lower floor but not the
standard one is a genuine, if shakier, angle -- it gets RISKY_PICK (with the
"keep this light" caution copy) rather than being thrown out as NO_BET. An
edge below the lower floor, or evidence the model itself flagged as
insufficient, still means no genuine case exists -- that is still NO_BET.
This is a threshold nuance, not a removal of NO_BET: on a day with truly
nothing defensible, NO_BET is still exactly what comes out.
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_STANDARD = "STANDARD_PICK"
RISK_RISKY = "RISKY_PICK"
# NO_BET is NO LONGER a pick classification (2026-07-25, Micah). It survives
# ONLY as the day-level marker meaning "no backable pick today", used by the
# generate_pick skip paths and downstream no-bet-day handling when fixtures/
# odds/data genuinely don't support any credible selection. classify() never
# returns it — every real candidate is STANDARD_PICK or RISKY_PICK.
RISK_NO_BET = "NO_BET"
VALID_RISK = {RISK_STANDARD, RISK_RISKY}

BET_INVESTOR = "INVESTOR_BET"
BET_PUNTER = "PUNTER_BET"
BET_GAMBLER = "GAMBLER_BET"
BET_NO_BET = "NO_BET"
VALID_BET_TYPE = {BET_INVESTOR, BET_PUNTER, BET_GAMBLER, BET_NO_BET}

CONFIDENCE_LEVELS = ("HIGH", "MODERATE", "LOW")

# Minimum edge (our estimated probability minus the bookmaker's implied
# probability, in percentage points) before a WIN-market selection is treated
# as a full-confidence standard pick. Below this on a straight win market
# nudges toward RISKY_PICK (not NO_BET) — see classify_risk.
MIN_EDGE_PCT = 5.0

# Backable floor (2026-07-25). A candidate is only worth featuring when the
# evidence is sufficient AND it shows at least a non-negative edge over the
# book — i.e. we are not backing a selection the bookmaker itself prices as
# more likely to lose than we do. This is the ONLY value gate now; it decides
# whether a candidate can be featured at all (is_backable), NOT its risk tier.
# Protective markets (draw-no-bet, double chance, handicaps, totals) are
# lower-variance, so a slim edge there is genuinely acceptable — the point of
# widening markets is that a credible, better-protected selection can be found
# on almost any day with real fixtures, instead of skipping to NO_BET.
MIN_VALUE_EDGE_PCT = 0.0

# Retained for backward-compatible imports/tests; no longer a NO_BET gate.
RISKY_MIN_EDGE_PCT = 2.5

# Odds thresholds used only to help pick a BET-TYPE bucket (tone), and as one
# of several signals feeding the RISK decision below. They are guidance, not
# hard cutoffs that disqualify a pick.
INVESTOR_ODDS_MAX = 2.20
GAMBLER_ODDS_MIN = 2.50

# How many distinct uncertainty flags before a pick is nudged into RISKY_PICK
# even when the raw edge number looks fine.
RISKY_UNCERTAINTY_THRESHOLD = 2


@dataclass
class Evidence:
    """Structured, evidence-only inputs — no copy/tone, no pre-baked labels."""
    evidence_sufficient: bool
    odds: float
    our_probability: float          # 0-100
    implied_probability: float      # 0-100
    confidence: str                 # HIGH | MODERATE | LOW  (evidence strength, not a vibe)
    uncertainty_flags: list = field(default_factory=list)  # short strings, e.g. "limited team news"
    # True for lower-variance / more protective markets — draw-no-bet, double
    # chance, handicaps (spreads) and totals. A protective market is not, by
    # itself, risky, and a slim edge on one is acceptable as a standard pick.
    protective_market: bool = False

    def __post_init__(self):
        self.confidence = (self.confidence or "LOW").upper()
        if self.confidence not in CONFIDENCE_LEVELS:
            self.confidence = "LOW"
        self.uncertainty_flags = list(self.uncertainty_flags or [])

    @property
    def edge_pct(self):
        return round(self.our_probability - self.implied_probability, 2)


@dataclass
class Classification:
    risk: str
    bet_type: str
    edge_pct: float
    confidence: str
    reasons: list


def is_backable(evidence: Evidence) -> tuple:
    """Is this candidate worth featuring AT ALL? Returns (backable, reason).

    This is the single value gate (2026-07-25) — it replaces the old
    NO_BET-from-classify_risk behaviour. A candidate is backable when the
    model had sufficient evidence AND the selection shows at least a
    non-negative edge over the bookmaker. Everything backable then gets a
    STANDARD_PICK or RISKY_PICK tier from classify_risk. When NOTHING is
    backable on a day with real fixtures, that is the genuine "no reliable
    data / no credible pick" case where the day is skipped — not a routine
    NO_BET on a game we could have found a protective angle in."""
    if not evidence.evidence_sufficient:
        return False, "insufficient evidence to support any selection"
    if evidence.edge_pct < MIN_VALUE_EDGE_PCT:
        return False, (
            f"no genuine value — our estimate ({evidence.our_probability:.0f}%) is not above "
            f"the book's implied probability ({evidence.implied_probability:.0f}%)"
        )
    return True, "backable"


def classify_risk(evidence: Evidence) -> tuple:
    """Returns (risk, reasons) — always STANDARD_PICK or RISKY_PICK, never
    NO_BET (backability is decided separately by is_backable). A pick is
    STANDARD unless one or more risk signals apply.

    Protective markets (draw-no-bet, double chance, handicaps, totals) are
    lower-variance: a slim edge on one is fine, and a bigger price on one is
    not automatically risky — so handicap/total/DNB/double-chance picks are
    NOT auto-classified risky (Micah 2026-07-25)."""
    reasons = []
    riskier_signals = 0

    if evidence.confidence == "LOW":
        riskier_signals += 1
        reasons.append("confidence in the evidence is low")

    if len(evidence.uncertainty_flags) >= RISKY_UNCERTAINTY_THRESHOLD:
        riskier_signals += 1
        reasons.append(f"{len(evidence.uncertainty_flags)} uncertainty factors noted")

    # A big price without high confidence to offset it is risky — but only on
    # a straight WIN market. A protective market at a bigger price is exactly
    # the kind of safer angle we now prefer, so it is not auto-risky.
    if (evidence.odds >= GAMBLER_ODDS_MIN and evidence.confidence != "HIGH"
            and not evidence.protective_market):
        riskier_signals += 1
        reasons.append("big price on a win market without high confidence to offset it")

    # A thin edge nudges a WIN-market pick toward risky. On a protective
    # (lower-variance) market a slim edge is acceptable as a standard pick,
    # so the thin-edge signal does not apply there.
    if evidence.edge_pct < MIN_EDGE_PCT and not evidence.protective_market:
        riskier_signals += 1
        reasons.append(
            f"edge {evidence.edge_pct:.1f}% is below the standard {MIN_EDGE_PCT:.0f}% bar on a win market"
        )

    if riskier_signals > 0:
        return RISK_RISKY, reasons

    reasons.append("evidence sufficient, edge and confidence both hold up")
    return RISK_STANDARD, reasons


def classify_bet_type(risk: str, evidence: Evidence) -> str:
    """Bet-type is a separate axis from risk — it describes the STYLE of the
    bet (tone on the public post), not how defensible it is."""
    if risk == RISK_NO_BET:
        return BET_NO_BET

    if evidence.odds <= INVESTOR_ODDS_MAX and evidence.confidence == "HIGH":
        return BET_INVESTOR

    if evidence.odds >= GAMBLER_ODDS_MIN:
        return BET_GAMBLER

    return BET_PUNTER


def classify(evidence: Evidence) -> Classification:
    risk, reasons = classify_risk(evidence)
    bet_type = classify_bet_type(risk, evidence)
    return Classification(
        risk=risk,
        bet_type=bet_type,
        edge_pct=evidence.edge_pct,
        confidence=evidence.confidence,
        reasons=reasons,
    )
