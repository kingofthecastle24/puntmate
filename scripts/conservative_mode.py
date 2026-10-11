"""
conservative_mode.py — PROPOSED high-strike-rate selection strategy.

2026-10-11 (external audit item 4): Micah's explicit brief was "a separate,
testable conservative strategy ranking well-supported candidates by
estimated win probability while retaining value/evidence checks... allow
prices below 1.50 but never equate low odds with safety", plus an explicit
instruction to NOT touch any live odds band, evidence rule, stake or edge
threshold without proposing it for review first, and NOT to restore the old
duplicate-persona renderer (replaced 2026-07-15 — see render_brand_templates
history). This module is the TESTABLE MECHANISM he asked for; the one
number it needs (CONSERVATIVE_MIN_PROBABILITY below) is a proposed default,
not a decided one, and this module is NOT wired into main.py's live run —
nothing here runs in production, publishes anything, or changes any
existing selection until Micah signs off on both the threshold and how (or
whether) its output should surface anywhere.

What this is NOT:
  - Not a cosmetic persona/voice — it's a second, independent RANKING over
    the exact same candidate pool generate_pick.py already builds (the
    `classified` list: every candidate that already passed is_backable()'s
    value/evidence gate at the live MIN_VALUE_EDGE_PCT, completely
    unchanged here).
  - Not an odds filter. Today's INVESTOR_BET tier uses odds <= 2.20 +
    confidence == HIGH (confirmed: no 1.50 floor anywhere in
    pick_classifier.py). This module doesn't touch that, and doesn't add
    its own odds ceiling/floor either — a 1.30 favourite and a 3.50
    outsider compete on the SAME basis here: estimated win probability and
    evidence strength, not price. "Short odds" and "safe" are different
    things; this module is built so it structurally cannot conflate them.

How it picks:
  1. Only candidates that already independently cleared is_backable() (risk
     != NO_BET in the classified list) are eligible at all — this never
     loosens or bypasses the value/evidence gate, it narrows further.
  2. Eligible candidates must ALSO be confidence == "HIGH" (the strongest
     evidence tier research_validator.py can award) AND our_probability >=
     CONSERVATIVE_MIN_PROBABILITY.
  3. Among what's left, the highest our_probability wins; ties broken by
     higher edge_pct (still backable, not just "likely").
  4. Nothing clears both bars -> an honest NO_BET for conservative mode,
     independent of whatever the standard daily pick turns out to be (it
     can easily feature today while conservative mode sits out, or the
     reverse).

PROPOSED, not decided: CONSERVATIVE_MIN_PROBABILITY. 65% is this module's
starting recommendation (comfortably above a coin-flip, achievable for
short-priced favourites AND for a well-supported pick at longer odds with
strong evidence) but it is explicitly NOT backtested or calibrated against
real settlement data yet — same caveat Micah already applied to
MIN_VALUE_EDGE_PCT's 2026-10-07 restore ("an inference, not a proven
cause"). Change this constant only after Micah has reviewed and approved a
specific number.
"""

CONSERVATIVE_MIN_PROBABILITY = 65.0  # PROPOSED — needs Micah's sign-off, see module docstring.
CONSERVATIVE_MIN_CONFIDENCE = "HIGH"


def select_conservative(classified, min_probability=None):
    """Returns the chosen candidate dict (same shape as generate_pick.py's
    `classified` entries) or None when nothing qualifies. `min_probability`
    defaults to CONSERVATIVE_MIN_PROBABILITY but is overridable per-call —
    purely so tests (and any future calibration run) can explore other
    thresholds without editing this module."""
    from pick_classifier import RISK_NO_BET

    threshold = CONSERVATIVE_MIN_PROBABILITY if min_probability is None else min_probability

    eligible = [
        c for c in classified
        if c["verdict"].risk != RISK_NO_BET
        and c["evidence"].confidence == CONSERVATIVE_MIN_CONFIDENCE
        and c["evidence"].our_probability >= threshold
    ]
    if not eligible:
        return None

    eligible.sort(key=lambda c: (-c["evidence"].our_probability, -c["evidence"].edge_pct))
    return eligible[0]
