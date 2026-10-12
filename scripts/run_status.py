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
