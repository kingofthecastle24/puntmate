#!/usr/bin/env python3
"""
inject_test_pick.py — TEST-ONLY. Writes a synthetic data/latest_run.json
using a fixed, realistic pick (no live odds/Claude calls) so the rest of the
pipeline (render -> freeze -> preview email -> approval gate) can be
exercised end-to-end without waiting for a real qualifying match.

Used by generate.yml's `force_test_pick` workflow_dispatch input — OFF by
default, never runs on the schedule, and never bypasses the approval gate or
DRY_RUN: it only replaces the "find a real pick" step. Everything after it
(render, freeze, checksums, email, approval, publish) runs unmodified.

This exists specifically to let Micah verify the Gmail preview email (final
image, caption, Telegram text, bet type, approval link) without depending on
a live match producing a genuine STANDARD/RISKY pick that day.
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from pick_classifier import Evidence, classify
from generate_pick import build_bet_type_reason, build_final_explanation, BET_TYPE_LABELS, RISK_PUBLIC_CAUTION

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
LATEST_RUN_PATH = os.path.join(REPO_ROOT, "data", "latest_run.json")

evidence = Evidence(
    evidence_sufficient=True,
    odds=2.10,
    our_probability=58,
    implied_probability=47.6,
    confidence="HIGH",
    uncertainty_flags=[],
)
verdict = classify(evidence)
reasoning_sentence = ("Warriors have won four of their last five at home and Storm are missing "
                       "two regular starters in the forward pack.")

pick = {
    "has_pick": True,
    "match": "Warriors vs Storm",
    "sport": "rugbyleague_nrl",
    "sport_label": "NRL",
    "home_team": "Warriors",
    "away_team": "Storm",
    "kickoff": datetime.now(timezone.utc).isoformat(),
    "selection": "WARRIORS",
    "market": "Head to Head",
    "odds": f"{evidence.odds:.2f}",
    "our_probability": evidence.our_probability,
    "implied_probability": evidence.implied_probability,
    "edge_pct": evidence.edge_pct,
    "risk": verdict.risk,
    "bet_type": verdict.bet_type,
    "bet_type_label": BET_TYPE_LABELS[verdict.bet_type],
    "bet_type_reason": build_bet_type_reason(verdict.bet_type, reasoning_sentence),
    "final_explanation": build_final_explanation(reasoning_sentence, verdict.risk, evidence.uncertainty_flags),
    "confidence": evidence.confidence,
    "confidence_label": evidence.confidence,
    "uncertainty_flags": evidence.uncertainty_flags,
    "public_caution": RISK_PUBLIC_CAUTION.get(verdict.risk),
    "research_warnings": ["TEST RUN — this pick is synthetic (scripts/inject_test_pick.py), injected via the force_test_pick workflow input to verify the approval-email flow. Not a real match assessment."],
    "big_game": False,
}

run_data = {
    "run_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    "run_ts": datetime.now(timezone.utc).isoformat(),
    "pick": pick,
}

os.makedirs(os.path.dirname(LATEST_RUN_PATH), exist_ok=True)
with open(LATEST_RUN_PATH, "w") as f:
    json.dump(run_data, f, indent=2)

print(f"TEST PICK injected: {pick['match']} | {pick['selection']} @ {pick['odds']} | "
      f"{pick['bet_type']} / {pick['risk']}")
