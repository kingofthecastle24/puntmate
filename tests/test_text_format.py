import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from text_format import truncate_at_sentence


class TruncateAtSentenceTests(unittest.TestCase):
    def test_text_within_limit_is_untouched(self):
        text = "Short and sweet."
        self.assertEqual(truncate_at_sentence(text, 100), text)

    def test_truncates_at_last_complete_sentence_within_limit(self):
        text = "First sentence here. Second sentence here. Third sentence here."
        result = truncate_at_sentence(text, 45)
        self.assertEqual(result, "First sentence here. Second sentence here.")
        self.assertTrue(result.endswith("."))

    def test_never_cuts_mid_word_when_a_sentence_boundary_exists(self):
        text = ("This is a third-place playoff — teams are emotionally drained, "
                "motivations are mixed, and sides in these situations often play "
                "conservatively. Getting four or more goals in a dead rubber like "
                "this is unlikely given how both sides typically approach these "
                "fixtures.")
        result = truncate_at_sentence(text, 400)
        self.assertEqual(result, text)  # fits whole, no cut needed at all
        self.assertNotIn("Getting four or…", result)

    def test_falls_back_to_word_boundary_only_when_no_sentence_fits(self):
        text = "word " * 200
        result = truncate_at_sentence(text.strip(), 50)
        self.assertTrue(result.endswith("…"))
        self.assertNotIn("wor…", result)
        self.assertLessEqual(len(result), 52)

    def test_empty_text(self):
        self.assertEqual(truncate_at_sentence("", 100), "")
        self.assertEqual(truncate_at_sentence(None, 100), "")


if __name__ == "__main__":
    unittest.main()
