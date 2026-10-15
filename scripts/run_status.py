"""
run_status.py — structured status/reason constants for one generate run.

Added 2026-10-11 (external audit, confirmed against the code): main.py's
only record of why a day produced no pick was a free-text "reasoning"
string. That collapsed genuinely different situations into one bucket —
"all candidates failed the value gate" and "the Odds API returned nothing
because the key died" both just looked like a quiet NO_BET day, with no
field anywhere distinguishing an operational failure from an honest
no-value day. These constants are that distinction; every run of main.py
now writes exactly one of them into data/latest_run.json's top-level
"status" field, on every path — including empty fixtures and API
failures, which previously wrote nothing at all (see main.py's module
docstring on the stale-latest_run.json bug this caused downstream).
"""

PICK_READY = "PICK_READY"              # a real pick was selected and rendered
NO_VALUE = "NO_VALUE"                  # fixtures + evidence existed; nothing cleared the edge bar
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # model had no usable basis for any candidate
BAD_ODDS = "BAD_ODDS"                  # candidates existed but odds couldn't be resolved
MODEL_ERROR = "MODEL_ERROR"            # the LLM call itself failed/refused/returned unparseable output
ODDS_API_ERROR = "ODDS_API_ERROR"      # The Odds API returned errors (not just "no fixtures")
RENDER_ERROR = "RENDER_ERROR"          # a pick was selected but card rendering failed entirely

ALL_STATUSES = {
    PICK_READY, NO_VALUE, INSUFFICIENT_EVIDENCE, BAD_ODDS,
    MODEL_ERROR, ODDS_API_ERROR, RENDER_ERROR,
}

# Statuses that represent an operational failure, not an honest "nothing to
# bet on today" — used to decide whether a run deserves an actionable alert
# (see main.py) rather than being treated as routine no-bet content.
OPERATIONAL_FAILURE_STATUSES = {BAD_ODDS, MODEL_ERROR, ODDS_API_ERROR, RENDER_ERROR}

# Content modes (2026-10-15 redesign, Section 7) — a SEPARATE axis from
# the status constants above. `status` says whether the pipeline operated
# normally; `content_mode` says what kind of public content (if any) this
# run's "pick" represents, so a reader (or the copy validator) can tell a
# real odds-backed pick apart from a research-only lead or a plain status
# update without re-deriving it from several other fields.
MODE_GATED_PICK = "GATED_PICK"          # odds-backed snapshot, existing classifier gate passed
MODE_NO_BET = "NO_BET"                  # no qualifying gated candidate today
MODE_RESEARCH_ONLY = "RESEARCH_ONLY"    # a verified research lead exists but isn't odds-gated (surfaced internally; see main.py's research_lead — public rendering/copy for this mode is a follow-up, not yet wired)
MODE_STATUS_ONLY = "STATUS_ONLY"        # no verified fixture/anchor or a research failure — honest no-pick update, no card

ALL_CONTENT_MODES = {MODE_GATED_PICK, MODE_NO_BET, MODE_RESEARCH_ONLY, MODE_STATUS_ONLY}

# Why Stage 2 (the odds-backed gate) didn't run this cycle, even though
# Stage 1 (research_shortlist.py) did — distinguishes a genuinely quiet
# day from a budget/operational constraint, which is the entire point of
# carrying a fallback_reason at all (Section 7: "distinguish quota
# exhaustion, invalid key, outage, mapping failure, no fixtures and gate
# rejection").
FALLBACK_NO_SPORT_SELECTED = "no_sport_selected"      # Stage 1 found nothing worth mapping to a sport key
FALLBACK_QUOTA_EXHAUSTED = "quota_exhausted"          # Stage 1 selected sports but the odds credit budget had no room
FALLBACK_RESEARCH_FAILED = "research_failed"          # Stage 1 itself errored or returned unusable output
