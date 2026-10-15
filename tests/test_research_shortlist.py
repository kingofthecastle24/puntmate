"""
Tests for research_shortlist.py (Stage 1 of the 2026-10-15 two-stage
redesign). The live Claude web-search call itself isn't exercised here
(no network, no API key in CI) -- these pin down the deterministic parts:
sanitizing a model's candidates (stripping anything gated-only), ranking
by evidence quality, selecting at most two distinct sport keys, and the
end-to-end run_research_shortlist() flow with the Anthropic client mocked.
"""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import research_shortlist as rs

REGISTRY = {
    "rugbyleague_nrl": {"label": "NRL", "markets": "h2h,spreads,totals", "max_credits": 3},
    "mma_mixed_martial_arts": {"label": "UFC/MMA", "markets": "h2h,totals", "max_credits": 2},
}


def _candidate(**overrides):
    base = {
        "fixture_id": "team-a-vs-team-b-2026-10-20",
        "sport_name": "NRL",
        "sport_key": "rugbyleague_nrl",
        "participants": ["Team A", "Team B"],
        "competition": "NRL",
        "kickoff_utc": "2026-10-20T08:00:00Z",
        "proposed_selection": "Team A",
        "market_type": "h2h",
        "research_reason": "Team A has won 4 of the last 5 meetings at home.",
        "uncertainty_flags": [],
        "source_refs": ["https://example.com/a"],
        "market_anchor": {
            "source": "Example Books", "favourite": "Team A", "selection": "Team A",
            "market": "h2h", "line": None, "price": 1.8,
            "observed_at_utc": "2026-10-19T00:00:00Z", "url": "https://example.com/odds",
        },
    }
    base.update(overrides)
    return base


class SanitizeCandidatesTests(unittest.TestCase):
    def test_strips_gated_only_fields(self):
        raw = [_candidate(our_probability=74, edge_pct=4.4)]
        clean = rs._sanitize_candidates(raw, REGISTRY)
        self.assertEqual(len(clean), 1)
        self.assertNotIn("our_probability", clean[0])
        self.assertNotIn("edge_pct", clean[0])

    def test_drops_candidates_missing_required_fields(self):
        raw = [_candidate(research_reason="")]
        self.assertEqual(rs._sanitize_candidates(raw, REGISTRY), [])

    def test_nulls_a_sport_key_not_in_the_registry(self):
        raw = [_candidate(sport_key="cricket_icc_world_cup")]
        clean = rs._sanitize_candidates(raw, REGISTRY)
        self.assertIsNone(clean[0]["sport_key"])

    def test_non_dict_entries_are_skipped_without_crashing(self):
        raw = [_candidate(), "not a dict", None, 42]
        clean = rs._sanitize_candidates(raw, REGISTRY)
        self.assertEqual(len(clean), 1)


class SelectSportKeysTests(unittest.TestCase):
    def test_empty_candidates_selects_nothing(self):
        self.assertEqual(rs.select_sport_keys([]), [])

    def test_candidates_with_no_sport_key_are_never_selected(self):
        cands = [_candidate(sport_key=None)]
        self.assertEqual(rs.select_sport_keys(cands), [])

    def test_caps_at_two_distinct_keys(self):
        cands = [
            _candidate(sport_key="rugbyleague_nrl", fixture_id="a"),
            _candidate(sport_key="mma_mixed_martial_arts", fixture_id="b"),
            _candidate(sport_key="rugbyleague_nrl", fixture_id="c"),  # duplicate key
        ]
        selected = rs.select_sport_keys(cands)
        self.assertEqual(len(selected), 2)
        self.assertEqual(set(selected), {"rugbyleague_nrl", "mma_mixed_martial_arts"})

    def test_better_evidence_ranks_first(self):
        weak = _candidate(sport_key="mma_mixed_martial_arts", fixture_id="weak",
                           source_refs=["https://example.com/one"],
                           uncertainty_flags=["thin coverage"], market_anchor=None)
        strong = _candidate(sport_key="rugbyleague_nrl", fixture_id="strong",
                             source_refs=["https://a", "https://b", "https://c"],
                             uncertainty_flags=[])
        selected = rs.select_sport_keys([weak, strong], max_selected=1)
        self.assertEqual(selected, ["rugbyleague_nrl"])


class ExtractJsonTests(unittest.TestCase):
    def test_extracts_fenced_json(self):
        text = 'Some reasoning text.\n```json\n{"candidates": []}\n```\n'
        self.assertEqual(rs._extract_json(text), {"candidates": []})

    def test_extracts_bare_json_object_as_fallback(self):
        text = 'blah {"candidates": []} blah'
        self.assertEqual(rs._extract_json(text), {"candidates": []})

    def test_raises_value_error_when_nothing_found(self):
        with self.assertRaises(ValueError):
            rs._extract_json("no json here at all")


class RunResearchShortlistTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_dir = rs.RESEARCH_DIR
        rs.RESEARCH_DIR = self._tmpdir.name

    def tearDown(self):
        rs.RESEARCH_DIR = self._orig_dir
        self._tmpdir.cleanup()

    def _mock_client(self, text, stop_reason="end_turn", usage=None):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text
        message = MagicMock()
        message.content = [text_block]
        message.stop_reason = stop_reason
        message.usage = usage
        stream_cm = MagicMock()
        stream_cm.__enter__.return_value.get_final_message.return_value = message
        client = MagicMock()
        client.messages.stream.return_value = stream_cm
        return client

    def test_happy_path_writes_record_and_selects_keys(self):
        payload = {
            "coverage_checked": ["NRL"],
            "coverage_unverified": [],
            "candidates": [_candidate()],
            "sources": ["https://example.com/a"],
            "warnings": [],
        }
        client = self._mock_client(f"```json\n{json.dumps(payload)}\n```")

        record = rs.run_research_shortlist(
            "run123", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )

        self.assertEqual(record["selected_sport_keys"], ["rugbyleague_nrl"])
        self.assertEqual(len(record["candidates"]), 1)
        path = os.path.join(rs.RESEARCH_DIR, "run123.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk["run_id"], "run123")

    def test_zero_candidates_selects_nothing(self):
        payload = {"coverage_checked": [], "coverage_unverified": list(REGISTRY), "candidates": [], "sources": [], "warnings": []}
        client = self._mock_client(f"```json\n{json.dumps(payload)}\n```")

        record = rs.run_research_shortlist(
            "run124", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )
        self.assertEqual(record["selected_sport_keys"], [])
        self.assertEqual(record["candidates"], [])

    def test_refusal_degrades_to_empty_record_not_a_crash(self):
        client = self._mock_client("", stop_reason="refusal")
        record = rs.run_research_shortlist(
            "run125", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )
        self.assertEqual(record["selected_sport_keys"], [])
        self.assertTrue(any("refusal" in w for w in record["warnings"]))

    def test_unparseable_response_degrades_to_empty_record_not_a_crash(self):
        client = self._mock_client("not json at all, sorry")
        record = rs.run_research_shortlist(
            "run126", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )
        self.assertEqual(record["selected_sport_keys"], [])
        self.assertTrue(any("could not be parsed" in w for w in record["warnings"]))

    def test_client_exception_degrades_to_empty_record_not_a_crash(self):
        client = MagicMock()
        client.messages.stream.side_effect = RuntimeError("network blip")
        record = rs.run_research_shortlist(
            "run127", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )
        self.assertEqual(record["selected_sport_keys"], [])
        self.assertTrue(any("research model call failed" in w for w in record["warnings"]))

    def test_model_cannot_smuggle_probability_into_the_persisted_record(self):
        payload = {
            "coverage_checked": [], "coverage_unverified": [],
            "candidates": [_candidate(our_probability=91, edge_pct=12.0)],
            "sources": [], "warnings": [],
        }
        client = self._mock_client(f"```json\n{json.dumps(payload)}\n```")
        record = rs.run_research_shortlist(
            "run128", "2026-10-20", "2026-10-20T00:00:00Z", "2026-10-21T00:00:00Z",
            REGISTRY, client=client,
        )
        self.assertNotIn("our_probability", record["candidates"][0])
        self.assertNotIn("edge_pct", record["candidates"][0])


if __name__ == "__main__":
    unittest.main()
