"""
text_format.py — shared text-formatting helpers used when preparing model
reasoning for public copy (Telegram/Instagram text) and for the graphic
cards.

BUG (found 2026-07-18, reported by Micah — France vs England, FIFA World
Cup, UNDER 3.5): the LIVE public Telegram post read "...Getting four or…
Worth knowing: ..." — the main reasoning sentence was hard-sliced at a
fixed character count and an ellipsis appended, cutting the thought off
mid-clause before a "Worth knowing:" caveat was appended right after it
with no natural break. Micah confirmed this has happened more than once,
not a one-off.

Root cause: two separate call sites each did their own naive character
truncation (generate_pick.py's _one_sentence() sliced at 160 chars via
rsplit(" ", 1); render_brand_templates.py's card "insight" prop sliced at
140 chars with no word-boundary handling at all). Neither respected sentence
boundaries, and Telegram/Instagram have no real length constraint at these
sizes (Telegram allows ~4096 chars/message, Instagram ~2200/caption) — the
truncation was serving the card's limited pixel space, but was being applied
upstream of BOTH the card render and the public post text, breaking the post
even though the post itself had plenty of room.

Fix: one shared, sentence-boundary-aware truncate function, used by both
call sites, so behaviour can't drift between them again.
"""

import re

_SENTENCE_END = re.compile(r'[.!?](?:\s|$)')


def truncate_at_sentence(text, max_len):
    """Return text unchanged if it already fits within max_len. Otherwise,
    truncate at the end of the LAST complete sentence that fits — never
    mid-word, mid-clause, or mid-sentence. Only falls back to a raw
    word-boundary cut (with a trailing ellipsis) if the text contains no
    sentence-ending punctuation at all within max_len — e.g. one long
    run-on with no full stop — since at that point there's no sentence
    boundary left to honour.
    """
    text = (text or "").strip()
    if len(text) <= max_len:
        return text

    fits = [m.end() for m in _SENTENCE_END.finditer(text) if m.end() <= max_len]
    if fits:
        return text[:fits[-1]].strip()

    cut = text[:max_len].rsplit(" ", 1)[0]
    return cut.rstrip(",.;") + "…"
