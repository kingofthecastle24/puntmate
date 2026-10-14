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
different bet-type bucket. Only insufficient evidence or failing the lane's
gate (see is_backable) produces NO_BET.

Note: an earlier design (Phase 3) had a second, lower edge floor
(RISKY_MIN_EDGE_PCT) that let a shakier-but-real edge through as RISKY_PICK
instead of NO_BET. RISKY_MIN_EDGE_PCT is kept only so old imports/tests
don't break; it is not read anywhere in this module's logic.

Per-lane gate (2026-10-14, see is_backable and GAMBLER_MIN_VALUE_EDGE_PCT /
INVESTOR_MIN_PROB_PCT / PUNTER_MIN_PROB_PCT below): is_backable is no longer
one flat edge floor for every candidate. Investor and punter lanes select
on the model's own win probability; the gambler lane alone keeps the old
value-edge bar. Every lane still requires a non-negative edge.
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

# Per-lane gate (2026-10-14, Micah: "I don't care about value, I care about
# being right - it should be based on level of confidence"). Eight straight
# No Bet days (7-14 Oct) under the old flat 7%-edge-for-everyone floor killed
# the whole funnel: no weekday picks, nothing compounding, no stake built for
# the weekend multi. Three advisors argued it out (see the spec this change
# came from): the investor/punter lanes now select on the model's own win
# probability (what Micah actually watches — strike rate), while the gambler
# lane keeps the old value-edge bar, since long-shot mispricing there is a
# real thing worth protecting. Every lane still requires sufficient evidence
# AND a non-negative edge — the one sanity rule kept from the old design:
# never back a selection the model itself rates below the book, under any
# philosophy.
#
# History: 2026-07-25 -> 2026-09-05 this floor was dropped to 0.0 (any
# non-negative edge), then restored to 7% on 2026-10-07 after the ledger
# showed a worse $ result (55.6% win rate but -$10.70, vs 45.8%/-$3.90
# before) on fewer, shorter-priced picks. That 7% floor now lives on as
# GAMBLER_MIN_VALUE_EDGE_PCT, for the gambler lane only.
GAMBLER_MIN_VALUE_EDGE_PCT = 7.0
MIN_VALUE_EDGE_PCT = GAMBLER_MIN_VALUE_EDGE_PCT  # kept for old imports/tests

# Per-lane model-probability floors (0-100 scale, same as
# Evidence.our_probability). These are starting numbers — the plan is to
# review them against real strike rate after a couple of weeks of data
# (calibration review) and adjust the constants, not the design.
INVESTOR_MIN_PROB_PCT = 70.0
PUNTER_MIN_PROB_PCT = 60.0

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


def is_backable(evidence: Evidence, bet_type: str) -> tuple:
    """Is this candidate worth featuring AT ALL? Returns (backable, reason).

    The gate is per-lane (2026-10-14): investor and punter lanes select on
    the model's own win probability (Micah: "I care about being right"),
    the gambler lane keeps the old value-edge bar. Every lane requires
    sufficient evidence and a non-negative edge — we never back a selection
    the model itself rates below the book, whatever the philosophy. When
    NOTHING is backable on a day with real fixtures, that is the genuine "no
    reliable data / no credible pick" case where the day is skipped."""
    if not evidence.evidence_sufficient:
        return False, "insufficient evidence to support any selection"

    if evidence.edge_pct < 0:
        # BUG FIX (2026-10-11, flagged by external audit): this used to say
        # our estimate "is not above" the book's — false whenever edge_pct
        # was positive but still under a floor. Kept honest here too: this
        # branch only ever fires on a genuinely negative edge now.
        return False, (
            f"edge too thin to back — our estimate ({evidence.our_probability:.0f}%) "
            f"is below the book's implied probability ({evidence.implied_probability:.0f}%)"
        )

    if bet_type == BET_GAMBLER:
        if evidence.edge_pct < GAMBLER_MIN_VALUE_EDGE_PCT:
            return False, (
                f"edge too thin to back for a gambler pick — our estimate "
                f"({evidence.our_probability:.0f}%) is only {evidence.edge_pct:.1f} points above the book's "
                f"implied probability ({evidence.implied_probability:.0f}%) — short of the "
                f"{GAMBLER_MIN_VALUE_EDGE_PCT:.0f}% floor"
            )
        return True, "backable"

    floor = INVESTOR_MIN_PROB_PCT if bet_type == BET_INVESTOR else PUNTER_MIN_PROB_PCT
    if evidence.our_probability < floor:
        lane = "investor" if bet_type == BET_INVESTOR else "punter"
        return False, (
            f"model confidence ({evidence.our_probability:.0f}%) is below the "
            f"{floor:.0f}% bar for {lane} picks"
        )
    return True, "backable"


def classify_risk(evidence: Evidence, bet_type: str) -> tuple:
    """Returns (risk, reasons) — always STANDARD_PICK or RISKY_PICK, never
    NO_BET (backability is decided separately by is_backable). A pick is
    STANDARD unless one or more risk signals apply.

    Protective markets (draw-no-bet, double chance, handicaps, totals) are
    lower-variance: a slim edge on one is fine, and a bigger price on one is
    not automatically risky — so handicap/total/DNB/double-chance picks are
    NOT auto-classified risky (Micah 2026-07-25).

    2026-10-14: the investor lane now selects on model probability, not
    edge size (see is_backable), so a small edge is the norm there, not a
    risk signal — flagging it would mark nearly every investor pick RISKY,
    which is just noise. The thin-edge signal is skipped for BET_INVESTOR
    only; punter and gambler keep it."""
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
    # and on the investor lane a small edge is expected by design (see the
    # docstring above), so the thin-edge signal does not apply to either.
    if evidence.edge_pct < MIN_EDGE_PCT and not evidence.protective_market and bet_type != BET_INVESTOR:
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
    bet (tone on the public post), not how defensible it is.

    2026-10-14 (Micah, decided): Investor no longer requires the HIGH
    confidence label. The research validator caps confidence at MODERATE
    whenever fewer than 3 sources validate, which was starving the lane
    Micah most wants flowing even on a genuinely strong 70%+ pick. Investor
    is now purely odds + the model's own win probability; the confidence
    label still shows on the post, it just doesn't gate the lane."""
    if risk == RISK_NO_BET:
        return BET_NO_BET

    if evidence.odds <= INVESTOR_ODDS_MAX and evidence.our_probability >= INVESTOR_MIN_PROB_PCT:
        return BET_INVESTOR

    if evidence.odds >= GAMBLER_ODDS_MIN:
        return BET_GAMBLER

    return BET_PUNTER


def classify(evidence: Evidence) -> Classification:
    # Bet type no longer depends on risk (the RISK_NO_BET branch above is
    # dead here — classify() is only ever called on a real candidate), so
    # compute it first: is_backable's per-lane gate (called by the caller,
    # generate_pick.py) needs to know the lane before it can gate on it, and
    # classify_risk's thin-edge exemption needs it too.
    bet_type = classify_bet_type(RISK_STANDARD, evidence)
    risk, reasons = classify_risk(evidence, bet_type)
    bet_type = classify_bet_type(risk, evidence)
    return Classification(
        risk=risk,
        bet_type=bet_type,
        edge_pct=evidence.edge_pct,
        confidence=evidence.confidence,
        reasons=reasons,
    )
