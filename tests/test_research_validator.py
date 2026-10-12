import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from research_validator import validate_snippets, assess_evidence_strength, SPORT_KEYWORDS
from fetch_news import ESPN_SPORT_MAP, RSS_SPORT_KEYWORD
from fetch_odds import SPORTS


class ResearchValidatorTests(unittest.TestCase):
    def test_rejects_cross_sport_contamination(self):
        # This is the exact real-world bug: NRL content for a football fixture.
        snippets = ["France NRL 2025 preview: Warriors edge trainers"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any("wrong sport" in w for w in warnings))

    def test_rejects_team_name_only_match(self):
        snippets = ["France announces new tourism campaign"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(accepted, [])

    def test_accepts_genuinely_relevant_snippet(self):
        snippets = ["France football squad injury update ahead of World Cup match"]
        accepted, warnings = validate_snippets(
            snippets, sport="soccer_fifa_world_cup", home_team="France", away_team="Spain"
        )
        self.assertEqual(len(accepted), 1)

    def test_confidence_ceiling_zero_sources(self):
        # Phase 1: zero validated news no longer caps at LOW — Claude is now
        # allowed to use general team/competition knowledge as supporting
        # context, so zero fresh snippets isn't "zero evidence" anymore.
        ceiling, warnings = assess_evidence_strength([])
        self.assertEqual(ceiling, "MODERATE")

    def test_confidence_ceiling_full_sources(self):
        ceiling, warnings = assess_evidence_strength(["a", "b", "c"], requested_count=3)
        self.assertEqual(ceiling, "HIGH")


class TestRugbyInternationalCoverageTests(unittest.TestCase):
    """2026-10-11: rugbyunion_international had no entry in SPORT_KEYWORDS or
    CROSS_SPORT_MARKERS at all, so every genuine Test-match snippet was
    rejected as 'team-name-only, no sport context' and confidence could
    never clear MODERATE (INVESTOR_BET requires HIGH) — see pick_classifier
    classify_bet_type. Flagged by an external audit; confirmed directly
    against the code, not taken on trust."""

    def test_genuine_test_rugby_headline_is_accepted(self):
        snippets = ["All Blacks confirm starting XV for Ireland test match at Eden Park"]
        accepted, warnings = validate_snippets(
            snippets, sport="rugbyunion_international", home_team="New Zealand", away_team="Ireland"
        )
        self.assertEqual(len(accepted), 1)

    def test_bare_country_name_with_no_rugby_context_is_still_rejected(self):
        # Must NOT accept merely because a team/country name appears.
        snippets = ["New Zealand announces new tourism campaign for international visitors"]
        accepted, warnings = validate_snippets(
            snippets, sport="rugbyunion_international", home_team="New Zealand", away_team="Ireland"
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any("no sport context" in w for w in warnings))

    def test_unrelated_sport_content_is_rejected(self):
        snippets = ["New Zealand Warriors edge out Storm in NRL golden point thriller"]
        accepted, warnings = validate_snippets(
            snippets, sport="rugbyunion_international", home_team="New Zealand", away_team="Ireland"
        )
        self.assertEqual(accepted, [])

    def test_three_genuine_sources_reach_high_confidence(self):
        snippets = [
            "All Blacks name starting lineup for Ireland test match",
            "Ireland rugby team travels to Eden Park ahead of test series decider",
            "Scrum battle set to define All Blacks v Ireland test match",
        ]
        accepted, warnings = validate_snippets(
            snippets, sport="rugbyunion_international", home_team="New Zealand", away_team="Ireland"
        )
        self.assertEqual(len(accepted), 3)
        ceiling, _ = assess_evidence_strength(accepted)
        self.assertEqual(ceiling, "HIGH")


class OtherSportCoverageAuditTests(unittest.TestCase):
    """2026-10-11: audited every sport in fetch_odds.SPORTS against
    SPORT_KEYWORDS — these were ALL missing a mapping (same bug class as
    rugbyunion_international), capping confidence at MODERATE regardless of
    how good the available research actually was."""

    def test_afl_snippet_accepted(self):
        accepted, _ = validate_snippets(
            ["Melbourne Demons name squad for AFL clash, key forward cleared to play"],
            sport="aussierules_afl", home_team="Melbourne Demons", away_team="Geelong Cats",
        )
        self.assertEqual(len(accepted), 1)

    def test_mlb_snippet_accepted(self):
        accepted, _ = validate_snippets(
            ["Atlanta Braves starting pitcher named ahead of MLB series opener"],
            sport="baseball_mlb", home_team="Atlanta Braves", away_team="Los Angeles Dodgers",
        )
        self.assertEqual(len(accepted), 1)

    def test_nhl_snippet_accepted(self):
        accepted, _ = validate_snippets(
            ["Carolina Hurricanes power play clicking ahead of NHL matchup"],
            sport="icehockey_nhl", home_team="Carolina Hurricanes", away_team="Washington Capitals",
        )
        self.assertEqual(len(accepted), 1)

    def test_unmapped_sport_bare_team_name_still_rejected(self):
        """Sanity check the audit didn't miss one: an unmapped sport key
        (not in fetch_odds.SPORTS) should still fail safe — never accept on
        team name alone."""
        accepted, warnings = validate_snippets(
            ["Some Team announces new sponsorship deal"],
            sport="not_a_real_sport_key", home_team="Some Team", away_team="Other Team",
        )
        self.assertEqual(accepted, [])

    def test_every_fetched_sport_has_keyword_and_news_source_coverage(self):
        """Regression guard (2026-10-11): this exact bug — a sport fetched
        for real odds but with no entry in SPORT_KEYWORDS/ESPN_SPORT_MAP/
        RSS_SPORT_KEYWORD — silently caps that sport's confidence at
        MODERATE forever, with no test ever failing to say so. If someone
        adds a new sport to fetch_odds.SPORTS without wiring up research
        coverage for it, this must fail loudly instead of waiting for
        another live-audit to notice."""
        missing_keywords = [s for s in SPORTS if s not in SPORT_KEYWORDS]
        missing_rss = [s for s in SPORTS if s not in RSS_SPORT_KEYWORD]
        self.assertEqual(missing_keywords, [], f"sports missing from SPORT_KEYWORDS: {missing_keywords}")
        self.assertEqual(missing_rss, [], f"sports missing from RSS_SPORT_KEYWORD: {missing_rss}")
        # ESPN coverage is best-effort (unverified path guesses, see
        # fetch_news.py's module docstring) — not required for every sport,
        # just checked here so a gap is visible rather than silent.
        missing_espn = [s for s in SPORTS if s not in ESPN_SPORT_MAP]
        if missing_espn:
            print(f"::notice::sports with no ESPN path mapping (RSS-only): {missing_espn}")


if __name__ == "__main__":
    unittest.main()
