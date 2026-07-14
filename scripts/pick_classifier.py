"""
pick_classifier.py — deterministic risk + bet-type classification.

This module never talks to an LLM. It takes the *evidence* an LLM (or a human)
has already extracted for a single candidate pick — probabilities, odds,
whether the evidence was actually sufficient, and any uncertainty flags — and
applies fixed, testable rules to decide two INDEPENDENT things:

  1. RISK classification  — how defensible/certain is this selection?
       STANDARD_PICK | RISKY_PICK | NO_BET
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
"""

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_STANDARD = "STANDARD_PICK"
RISK_RISKY = "RISKY_PICK"
RISK_NO_BET = "NO_BET"
VALID_RISK = {RISK_STANDARD, RISK_RISKY, RISK_NO_BET}

BET_INVESTOR = "INVESTOR_BET"
BET_PUNTER = "PUNTER_BET"
BET_GAMBLER = "GAMBLER_BET"
BET_NO_BET = "NO_BET"
VALID_BET_TYPE = {BET_INVESTOR, BET_PUNTER, BET_GAMBLER, BET_NO_BET}

CONFIDENCE_LEVELS = ("HIGH", "MODERATE", "LOW")

# Minimum edge (our estimated probability minus the bookmaker's implied
# probability, in percentage points) before a selection is worth backing at
# all. Below this, there is no genuine value case regardless of confidence.
MIN_EDGE_PCT = 5.0

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


def classify_risk(evidence: Evidence) -> tuple:
    """Returns (risk, reasons)."""
    reasons = []

    if not evidence.evidence_sufficient:
        return RISK_NO_BET, ["insufficient evidence to support any selection"]

    if evidence.edge_pct < MIN_EDGE_PCT:
        return RISK_NO_BET, [f"edge {evidence.edge_pct:.1f}% is below the {MIN_EDGE_PCT:.0f}% minimum"]

    # From here, evidence is sufficient AND the edge clears the bar — this is
    # always at least a defensible pick. Whether it's STANDARD or RISKY comes
    # down to how much uncertainty is layered on top.
    riskier_signals = 0

    if evidence.confidence == "LOW":
        riskier_signals += 1
        reasons.append("confidence in the evidence is low")

    if len(evidence.uncertainty_flags) >= RISKY_UNCERTAINTY_THRESHOLD:
        riskier_signals += 1
        reasons.append(f"{len(evidence.uncertainty_flags)} uncertainty factors noted")

    if evidence.odds >= GAMBLER_ODDS_MIN and evidence.confidence != "HIGH":
        # Big price AND we're not fully confident — riskier, but not
        # disqualifying. (Big price + HIGH confidence + sufficient evidence
        # is a genuine standard pick that happens to pay well.)
        riskier_signals += 1
        reasons.append("odds outside the normal comfort range without high confidence to offset it")

    if riskier_signals > 0:
        return RISK_RISKY, reasons

    reasons.append("evidence sufficient, edge clears the minimum, confidence and odds both check out")
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
