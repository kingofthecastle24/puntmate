"""
research_shortlist.py — Stage 1 of the two-stage pipeline (2026-10-15
redesign: "research first, price second").

Run #206 burned the Odds API account's entire monthly free-tier
allowance (500/500 credits) by scanning all 14 registered sports on
every single run. This module is the fix on the "discovery" side: before
ANY paid Odds API call, use Claude's web-search tool to discover what's
actually in season worldwide (not just the 14 registered sport keys),
verify a handful of real candidates with a genuine public market anchor,
and shortlist AT MOST two sport keys for Stage 2 (fetch_odds.py) to
actually query. Zero candidates means an empty key list and zero paid
odds calls that run — a quiet day costs nothing.

This module NEVER estimates a win probability or an edge. Those fields
are Stage 2's job (the unchanged pick_classifier.py gate), applied only
to odds-backed candidates. Enforced here, not just documented: any
probability/edge-shaped field a model response tries to smuggle into a
candidate is stripped in _sanitize_candidates before the record is ever
written or returned.

See the 15 Oct 2026 implementation spec, Section 3, for the full design
this implements.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

import anthropic

sys.path.insert(0, os.path.dirname(__file__))
from nz_date import nz_now_iso

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
RESEARCH_DIR = os.path.join(REPO_ROOT, "data", "research")

SCHEMA_VERSION = 1
MAX_SELECTED_SPORT_KEYS = 2
# $2/$10 per MTok input/output, matching the design doc's Section 8 cost
# model (a current-generation Sonnet; the existing gate in generate_pick.py
# stays on claude-opus-5 and is deliberately NOT touched by this module).
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_MAX_WEB_SEARCHES = 6
DEFAULT_MAX_TOKENS = 8000

# Fields that belong to Stage 2 (the odds-backed gate) ONLY. A Stage 1
# candidate carrying any of these is a model that forgot its lane -- they
# are stripped, never trusted, regardless of what the model wrote.
_GATED_ONLY_FIELDS = (
    "our_probability", "implied_probability", "edge_pct", "edge",
    "win_probability", "probability", "confidence_ceiling_pct",
)

REQUIRED_CANDIDATE_FIELDS = (
    "fixture_id", "sport_name", "participants", "competition", "kickoff_utc",
    "proposed_selection", "market_type", "research_reason",
)

SYSTEM_PROMPT = """You are PuntMate's Stage 1 research scout. Your ONLY \
job is DISCOVERY and VERIFICATION of upcoming sports fixtures worldwide \
-- you never price a bet, estimate a win probability, or compute an edge. \
That happens later, by a different, deterministic system, only for the \
sports you shortlist here.

Rules:
1. Search broadly across sports and competitions that are ACTUALLY IN \
SEASON right now worldwide -- do not limit yourself to the registry list \
you're given below. The registry is only used LATER, to map a shortlisted \
sport back to an Odds API query key -- it is not a boundary on what you \
may discover.
2. Verify every candidate you propose: exact competition, exact \
participants, exact kickoff time, from retrievable sources. A search \
snippet alone is a lead, not a confirmed fact -- follow it to a real page \
before treating it as evidence. Keep the URL and an observation time for \
anything you rely on.
3. For each candidate, try to find a lawful PUBLIC market anchor: a \
bookmaker or odds-information source, the market favourite, the \
selection, the market type and line, the decimal price, and when you \
observed it, with its URL. If you cannot find one, leave market_anchor \
null -- never invent one.
4. Rank candidates by evidence quality and research strength (how well \
verified the fixture and context are), NOT by any numeric win \
probability or edge -- you must not compute or state either of those; \
that is explicitly not your job.
5. Select at most two sport keys from the registry below that your \
strongest candidates map to (prefer one when a second would add little). \
A candidate that doesn't map to any registry key can still be reported \
(sport_key null) but cannot be one of the selected keys.
6. If you genuinely find nothing worth proposing, return an empty \
candidates list. Never invent a fixture or a source to fill the list.

End your response with EXACTLY ONE fenced ```json code block containing \
an object with this shape and nothing else outside the fence:
{
  "coverage_checked": ["sports/competitions you actually searched"],
  "coverage_unverified": ["sports you didn't get to -- be honest about this"],
  "candidates": [
    {
      "fixture_id": "stable id you invent, e.g. slugified participants+date",
      "sport_name": "human sport name",
      "sport_key": "registry key if one matches, else null",
      "participants": ["Team A", "Team B"],
      "competition": "competition name",
      "kickoff_utc": "ISO-8601 UTC timestamp",
      "proposed_selection": "what you'd flag, in plain words",
      "market_type": "h2h | spread | total | other",
      "line": "the line/handicap/total if applicable, else null",
      "research_reason": "1-3 sentences on WHY this fixture, not a probability",
      "uncertainty_flags": ["anything that makes you less sure"],
      "source_refs": ["https://... retrieval URLs you actually used"],
      "market_anchor": {
        "source": "bookmaker or odds-info source name",
        "favourite": "team/selection the anchor favours",
        "selection": "the specific selection the anchor prices",
        "market": "market type",
        "line": "line if applicable, else null",
        "price": "decimal odds as a number",
        "observed_at_utc": "ISO-8601 UTC timestamp",
        "url": "https://..."
      }
    }
  ],
  "sources": ["every URL you retrieved, even ones you didn't use"],
  "warnings": ["anything worth flagging about this run's coverage"]
}
"""


def _registry_summary(registry):
    """registry: {sport_key: {"label": ..., "markets": "h2h,...", "max_credits": N}}."""
    lines = []
    for key, info in sorted(registry.items()):
        lines.append(f"- {info.get('label', key)} -> sport_key \"{key}\" "
                      f"(markets: {info.get('markets', 'h2h')}, max credits: {info.get('max_credits', 1)})")
    return "\n".join(lines) or "(registry is currently empty)"


def _build_prompt(business_date_nz, window_start_utc, window_end_utc, registry, already_actioned_slugs):
    already = sorted(already_actioned_slugs or [])
    already_text = (
        "\n\nFixtures already actioned in the last few days (exclude these, find something new): "
        + ", ".join(already)
    ) if already else ""
    return (
        f"Business date (NZ): {business_date_nz}\n"
        f"Fixture window (UTC): {window_start_utc} to {window_end_utc}\n\n"
        f"Current seasonal registry (for mapping ONLY -- see rule 1 above):\n"
        f"{_registry_summary(registry)}"
        f"{already_text}\n\n"
        "Find and verify this window's most promising fixtures across sports actually "
        "in season worldwide, then follow the output format exactly."
    )


def _extract_json(text):
    """Same tolerant extraction as generate_pick.py's own _extract_json --
    a fenced ```json block if present, else the first top-level {...}."""
    fence = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in research response")
    return json.loads(text[start:end + 1])


def _sanitize_candidates(raw_candidates, registry):
    """Drop anything gated-only (probability/edge), require the minimum
    evidence fields, and null out any sport_key that isn't actually in
    today's registry -- a model can suggest a key, it can't invent one."""
    clean = []
    for c in raw_candidates or []:
        if not isinstance(c, dict):
            continue
        if not all(c.get(f) for f in REQUIRED_CANDIDATE_FIELDS):
            continue
        c = {k: v for k, v in c.items() if k not in _GATED_ONLY_FIELDS}
        sport_key = c.get("sport_key")
        if sport_key not in registry:
            c["sport_key"] = None
        c.setdefault("uncertainty_flags", [])
        c.setdefault("source_refs", [])
        c.setdefault("market_anchor", None)
        c.setdefault("line", None)
        clean.append(c)
    return clean


def _evidence_rank_key(candidate):
    """Rank by evidence quality, not any numeric probability (none exists
    at Stage 1): more sources and a real market anchor rank higher, more
    uncertainty flags ranks lower. Ties keep input order (stable sort)."""
    anchor_bonus = 0 if candidate.get("market_anchor") else 1
    return (anchor_bonus, -len(candidate.get("source_refs") or []), len(candidate.get("uncertainty_flags") or []))


def select_sport_keys(candidates, max_selected=MAX_SELECTED_SPORT_KEYS):
    """At most `max_selected` DISTINCT, non-null sport keys, taken from
    candidates in evidence-quality order. Zero candidates -> empty list,
    which is what makes fetch_upcoming_odds([], ...) cost nothing."""
    ranked = sorted([c for c in candidates if c.get("sport_key")], key=_evidence_rank_key)
    selected = []
    for c in ranked:
        key = c["sport_key"]
        if key not in selected:
            selected.append(key)
        if len(selected) >= max_selected:
            break
    return selected


def _usage_dict(usage):
    if usage is None:
        return {}
    server_tool_use = getattr(usage, "server_tool_use", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "web_search_requests": getattr(server_tool_use, "web_search_requests", None) if server_tool_use else None,
    }


def _empty_record(run_id, business_date_nz, window_start_utc, window_end_utc, registry, warnings, model=None):
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "business_date_nz": business_date_nz,
        "researched_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "registry_version": sorted(registry.keys()),
        "coverage_checked": [],
        "coverage_unverified": sorted(registry.keys()),
        "selected_sport_keys": [],
        "candidates": [],
        "sources": [],
        "warnings": warnings,
        "model": model,
        "usage": {},
    }


def _write_record(run_id, record):
    os.makedirs(RESEARCH_DIR, exist_ok=True)
    path = os.path.join(RESEARCH_DIR, f"{run_id}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path


def run_research_shortlist(run_id, business_date_nz, window_start_utc, window_end_utc, registry,
                            already_actioned_slugs=None, model=None,
                            max_web_searches=DEFAULT_MAX_WEB_SEARCHES, max_tokens=DEFAULT_MAX_TOKENS,
                            client=None):
    """Runs Stage 1 and persists data/research/<run_id>.json. Always
    returns a record dict, even on a model/parse failure -- a research
    failure degrades to an empty shortlist (zero odds calls), never a
    crash (main.py's own STATUS_ONLY fallback decides what the public
    content looks like on a day like that)."""
    model = model or os.environ.get("RESEARCH_MODEL", DEFAULT_MODEL)
    client = client or anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _build_prompt(business_date_nz, window_start_utc, window_end_utc, registry, already_actioned_slugs)

    try:
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT,
            tools=[{"type": "web_search_20260209", "name": "web_search", "max_uses": max_web_searches}],
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            message = stream.get_final_message()
    except Exception as e:  # noqa: BLE001 -- a research failure must never crash the run
        record = _empty_record(run_id, business_date_nz, window_start_utc, window_end_utc, registry,
                                [f"research model call failed: {e}"], model)
        _write_record(run_id, record)
        return record

    stop_reason = getattr(message, "stop_reason", None)
    text_block = next((b for b in message.content if getattr(b, "type", None) == "text"), None)
    usage = _usage_dict(getattr(message, "usage", None))

    if stop_reason == "refusal" or text_block is None:
        record = _empty_record(run_id, business_date_nz, window_start_utc, window_end_utc, registry,
                                [f"research model returned no usable text (stop_reason={stop_reason})"], model)
        record["usage"] = usage
        _write_record(run_id, record)
        return record

    try:
        parsed = _extract_json(text_block.text)
    except (json.JSONDecodeError, ValueError) as e:
        record = _empty_record(run_id, business_date_nz, window_start_utc, window_end_utc, registry,
                                [f"research response could not be parsed as JSON: {e}"], model)
        record["usage"] = usage
        _write_record(run_id, record)
        return record

    candidates = _sanitize_candidates(parsed.get("candidates", []), registry)
    selected = select_sport_keys(candidates)

    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "business_date_nz": business_date_nz,
        "researched_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "registry_version": sorted(registry.keys()),
        "coverage_checked": parsed.get("coverage_checked", []),
        "coverage_unverified": parsed.get("coverage_unverified", []),
        "selected_sport_keys": selected,
        "candidates": candidates,
        "sources": parsed.get("sources", []),
        "warnings": parsed.get("warnings", []),
        "model": model,
        "usage": usage,
    }
    _write_record(run_id, record)
    return record
