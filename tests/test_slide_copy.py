import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import generate_picks_image as gpi

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRAND_DIR = os.path.join(REPO_ROOT, "brand", "Templates")

BETSLIP_NIGHT = os.path.join(BRAND_DIR, "PuntMate Bet Post - Betslip Night.dc.html")
MATCHDAY_PRINT = os.path.join(BRAND_DIR, "PuntMate Bet Post - Matchday Print.dc.html")
SOCIAL_TEMPLATES = os.path.join(BRAND_DIR, "PuntMate Social Templates.dc.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class SlideCopyCleanupTests(unittest.TestCase):
    """2026-07-19 (Micah): remove the 'Pick of the Week'/'Pick of the Day'
    style framing from the slides, and remove the Instagram Story's
    'SWIPE UP →' CTA since a static image post has nothing to actually
    swipe up to (no real link sticker attached)."""

    def test_python_cover_themes_no_longer_says_daily(self):
        theme = gpi.COVER_THEMES["Daily Pick"]
        # 2026-07-20 (Micah): DAILY PICK LOCKED is back by request — the
        # earlier removal went further than he wanted (only "Pick of the
        # Week"/"Tip of the Week" framing should be gone).
        self.assertEqual(theme["kicker"], "PUNTMATE'S DAILY PICK")
        self.assertEqual(tuple(theme["lines"]), ("DAILY", "PICK", "LOCKED"))

    def test_story_template_never_shows_tip_of_the_week(self):
        # The Story kicker was a literal hardcoded string (no theme system
        # at all) — must be gone entirely from that template.
        self.assertNotIn("TIP OF THE WEEK", _read(SOCIAL_TEMPLATES).upper())

    def test_feed_cover_no_longer_defaults_to_tip_of_the_week(self):
        # Betslip Night / Matchday Print keep "Tip of the Week" as one
        # SELECTABLE option in the design tool's Tweaks panel (a designer
        # can still manually choose it for a one-off post) — but it must no
        # longer be the DEFAULT that ships when nothing overrides coverTheme,
        # since our pipeline always explicitly sets "Daily Pick" anyway.
        for path in (BETSLIP_NIGHT, MATCHDAY_PRINT):
            html = _read(path)
            self.assertIn('&quot;default&quot;: &quot;Daily Pick&quot;', html)
            self.assertNotIn('&quot;default&quot;: &quot;Tip of the Week&quot;', html)

    def test_no_daily_pick_headline_copy_in_brand_templates(self):
        for path in (BETSLIP_NIGHT, MATCHDAY_PRINT):
            html = _read(path)
            self.assertIn("PUNTMATE'S DAILY PICK", html)
            self.assertIn("l1: 'DAILY'", html)

    def test_no_dead_swipe_up_cta_in_story_template(self):
        html = _read(SOCIAL_TEMPLATES)
        self.assertNotIn("SWIPE UP", html.upper())

    def test_swipe_arrow_to_next_slide_is_untouched(self):
        """The feed carousel's 'SWIPE →' / 'SWIPE FOR THE PICK →' CTAs point
        to a real next slide within the same post — those are legitimate
        and must NOT be removed, only the Story's dead swipe-up."""
        betslip = _read(BETSLIP_NIGHT)
        matchday = _read(MATCHDAY_PRINT)
        self.assertTrue("SWIPE" in betslip.upper())
        self.assertTrue("SWIPE FOR THE PICK" in matchday.upper())

    def test_theme_fallback_no_longer_defaults_to_tip_of_the_week(self):
        for path in (BETSLIP_NIGHT, MATCHDAY_PRINT):
            html = _read(path)
            self.assertNotIn("?? themes['Tip of the Week']", html)


if __name__ == "__main__":
    unittest.main()
