"""
generate_picks_image.py — PuntMate NZ brand-compliant carousel generator.

Generates 3-slide PNG carousels matching the PuntMate Brand Kit v2:
  - Betslip Night (dark): everyday default
  - Matchday Print (cream/red): big games, finals, UFC, World Cup knockouts

Slide structure:
  Slide 1 — Cover:  sport tag + cover kicker + big headline + "SWIPE →"
  Slide 2 — The Tip: betslip card (MATCH / SELECTION / DECIMAL ODDS)
  Slide 3 — The Breakdown: analysis + confidence dots + risk tagline + follow CTA

Fonts required in ../fonts/:
  Archivo-Black.ttf        (cover headlines, wordmark)
  SpaceGrotesk-Bold.ttf    (match names, selection)
  SpaceGrotesk-Medium.ttf  (body text, analysis)
  SpaceMono-Bold.ttf       (odds, labels, tags)
  SpaceMono-Regular.ttf    (muted labels)

If fonts are missing, falls back to system defaults gracefully.
"""

import os
import re
import math
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'fonts')
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')
BRAND_KIT_DIR = os.path.join(os.path.dirname(__file__), '..', 'Brand Kit', 'Logo')

W, H = 1080, 1350  # logical canvas dimensions (all coordinate math uses these)
S = 2              # Supersampling scale: render at W*S × H*S, downscale with LANCZOS


def _sp(v):
    """Convert a logical coordinate or (x, y) pair to physical canvas pixels."""
    if isinstance(v, (int, float)):
        return int(round(v * S))
    return tuple(int(round(x * S)) for x in v)


class ScaledDraw:
    """
    Wraps ImageDraw and transparently scales all coordinates and line widths by S.
    All callers use logical 1× coordinates; this converts to physical at draw time.
    textbbox() divides the physical result by S, so callers always work in logical space.
    """

    def __init__(self, draw):
        self._d = draw

    @staticmethod
    def _s(v):
        if isinstance(v, (int, float)):
            return int(round(v * S))
        if isinstance(v, (list, tuple)):
            return type(v)(ScaledDraw._s(x) for x in v)
        return v

    def text(self, xy, text, font=None, fill=None, **kw):
        self._d.text(self._s(xy), text, font=font, fill=fill, **kw)

    def textbbox(self, xy, text, font=None, **kw):
        phys = self._d.textbbox(self._s(xy), text, font=font, **kw)
        return tuple(int(round(v / S)) for v in phys)

    def line(self, xy, fill=None, width=1, joint=None, **kw):
        kw2 = {'fill': fill, 'width': max(1, self._s(width))}
        if joint:
            kw2['joint'] = joint
        self._d.line(self._s(xy), **kw2)

    def rectangle(self, xy, fill=None, outline=None, width=1, **kw):
        self._d.rectangle(self._s(xy), fill=fill, outline=outline,
                          width=max(1, self._s(width)))

    def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, **kw):
        self._d.rounded_rectangle(self._s(xy), radius=self._s(radius),
                                  fill=fill, outline=outline,
                                  width=max(1, self._s(width)))

    def ellipse(self, xy, fill=None, outline=None, width=1, **kw):
        kwargs = {}
        if fill is not None:
            kwargs['fill'] = fill
        if outline is not None:
            kwargs['outline'] = outline
            kwargs['width'] = max(1, self._s(width))
        self._d.ellipse(self._s(xy), **kwargs)


# ── Font loader ───────────────────────────────────────────────────────────────

def _f(name, size):
    """Load a font at logical size. Internally scales by S for the physical canvas."""
    phys_size = int(size * S)
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, phys_size)
        except Exception:
            pass
    fallbacks = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, phys_size)
            except Exception:
                pass
    return ImageFont.load_default()


def _save(img, path):
    """Downscale from physical canvas (W*S × H*S) to output resolution (W × H) and save."""
    out = img.resize((W, H), Image.LANCZOS)
    out.save(path, "PNG", optimize=True)
    print(f"  Saved: {path}")


# ── Colour palettes ───────────────────────────────────────────────────────────

# Betslip Night accents — rotate each post
NIGHT_ACCENTS = {
    "green": {"accent": "#35E07E", "accent_dim": "#1A5C38", "glow": "#35E07E66"},
    "blue":  {"accent": "#3DB2FF", "accent_dim": "#1A3D5C", "glow": "#3DB2FF66"},
    "amber": {"accent": "#FFC145", "accent_dim": "#5C4200", "glow": "#FFC14566"},
    "pink":  {"accent": "#FF4FA3", "accent_dim": "#5C1A3D", "glow": "#FF4FA366"},
}

# Fixed night palette
NIGHT = {
    "bg":      "#0B0F0D",
    "surface": "#111815",
    "text":    "#EAF7EF",
    "muted":   "#6B7A72",
    "dimmer":  "#3A4A40",
}

# Matchday Print palette (fixed — no rotation)
PRINT = {
    "bg":      "#F4EEE2",
    "ink":     "#16130F",
    "red":     "#E8402A",
    "yellow":  "#FFD400",
    "muted":   "#8C8070",
}


# ── Cover theme map — kicker + 3 headline lines (matches brand template exactly) ─

COVER_THEMES = {
    "Tip of the Week":    {"kicker": "TIP OF THE WEEK",         "lines": ("BEST",  "VALUE",  "BET.")},
    "Multi Monday":       {"kicker": "MULTI MONDAY",            "lines": ("THE",   "MULTI",  "IS ON.")},
    "Daily Pick":         {"kicker": "PUNTMATE'S DAILY PICK",   "lines": ("DAILY", "PICK",   "LOCKED")},
    "Banker of the Day":  {"kicker": "BANKER OF THE DAY",       "lines": ("THE",   "BANKER", "IS IN.")},
    "Value Alert":        {"kicker": "VALUE ALERT",             "lines": ("VALUE", "ALERT",  "LIVE.")},
}

# Confidence labels (risk framing) — matches template JS
CONFIDENCE_RISK = {5: "MINIMAL", 4: "LOW", 3: "MODERATE", 2: "HIGHER", 1: "SPECULATIVE"}

# Confidence level — simple 3-tier label for top-right display
CONFIDENCE_LEVEL = {5: "HIGH", 4: "HIGH", 3: "MEDIUM", 2: "LOW", 1: "LOW"}

# Legacy alias kept so old callers don't break
COVER_HEADLINES = {k: v["lines"] for k, v in COVER_THEMES.items()}


# ── Utility drawing helpers ───────────────────────────────────────────────────

def _rrect(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _text_center(draw, text, y, font, fill, width=W):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, y), text, font=font, fill=fill)


def _draw_grid(draw, color=(255, 255, 255, 7), cell=60):
    """Retained for legacy calls — no longer draws anything (user removed grid)."""
    pass


def _load_logo(size):
    """Load the brand badge PNG at given pixel size. Returns RGBA Image or None."""
    for candidate in [
        os.path.join(BRAND_KIT_DIR, 'puntmate-icon-badge.png'),
        os.path.join(ASSETS_DIR, 'logo.png'),
    ]:
        if os.path.exists(candidate):
            try:
                logo = Image.open(candidate).convert("RGBA")
                phys = int(size * S)
                logo = logo.resize((phys, phys), Image.LANCZOS)
                return logo
            except Exception:
                pass
    return None


def _load_lockup(height):
    """Load the brand lockup (badge+wordmark) PNG scaled to given height. Returns RGBA Image or None."""
    candidate = os.path.join(BRAND_KIT_DIR, 'puntmate-lockup.png')
    if os.path.exists(candidate):
        try:
            img = Image.open(candidate).convert("RGBA")
            w, h = img.size
            phys_h = int(height * S)
            new_w = int(w * phys_h / h)
            return img.resize((new_w, phys_h), Image.LANCZOS)
        except Exception:
            pass
    return None


def _draw_value_arrow(draw, cx, cy, size, color):
    """Draw the PuntMate value-arrow logo mark (rising trend line + arrowhead)."""
    s = size / 120
    pts = [
        (int(cx + (22 - 60) * s), int(cy + (84 - 60) * s)),
        (int(cx + (54 - 60) * s), int(cy + (52 - 60) * s)),
        (int(cx + (72 - 60) * s), int(cy + (70 - 60) * s)),
        (int(cx + (100 - 60) * s), int(cy + (30 - 60) * s)),
    ]
    draw.line(pts, fill=color, width=max(2, int(17 * s)), joint="curve")
    # Arrowhead lines
    tip = pts[-1]
    draw.line([tip, (int(cx + (74 - 60) * s), int(cy + (30 - 60) * s))], fill=color, width=max(2, int(17 * s)))
    draw.line([tip, (int(cx + (100 - 60) * s), int(cy + (56 - 60) * s))], fill=color, width=max(2, int(17 * s)))


def _draw_confidence_dots(draw, cx, y, value, total=5, accent="#35E07E"):
    """Draw confidence meter as filled/empty dots."""
    size = 20
    gap = 10
    total_w = total * size + (total - 1) * gap
    x = cx - total_w // 2
    for i in range(total):
        fill = accent if i < value else NIGHT["dimmer"]
        draw.ellipse([x, y, x + size, y + size], fill=fill)
        x += size + gap


def _wordmark(draw, x, y, size, accent):
    """Draw PUNTMATE wordmark: PUNT (white) + MATE (accent)."""
    f = _f("Archivo-Black.ttf", size)
    draw.text((x, y), "PUNT", font=f, fill="#EAF7EF")
    bbox = draw.textbbox((x, y), "PUNT", font=f)
    draw.text((bbox[2], y), "MATE", font=f, fill=accent)


# ── Slide generators — Betslip Night ─────────────────────────────────────────

def _night_slide1_cover(pick):
    """Betslip Night — Cover slide with grid, big headline, sport tag."""
    palette = NIGHT_ACCENTS.get(pick.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent = palette["accent"]
    accent_dim = palette["accent_dim"]

    img = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))
    _draw_grid(draw)

    pad = 88

    # Top bar — lockup PNG (badge+wordmark) + sport tag pill
    lockup = _load_lockup(64)
    logo_y = pad - 8
    if lockup:
        img.paste(lockup, _sp((pad, logo_y)), lockup)
    else:
        # Fallback: draw badge circle + wordmark
        badge_cx, badge_cy, badge_r = pad + 32, logo_y + 32, 32
        draw.ellipse([badge_cx - badge_r, badge_cy - badge_r,
                      badge_cx + badge_r, badge_cy + badge_r],
                     fill=NIGHT["surface"], outline=accent_dim, width=2)
        _draw_value_arrow(draw, badge_cx, badge_cy, badge_r * 1.8, accent)
        _wordmark(draw, pad + 74, logo_y + 18, 30, accent)

    # Sport tag pill — right-aligned, vertically centred with lockup
    sport = pick.get("sport_label", "SPORT")
    tag_f = _f("SpaceGrotesk-Bold.ttf", 22)
    tag_bbox = draw.textbbox((0, 0), sport, font=tag_f)
    text_w = tag_bbox[2] - tag_bbox[0]
    text_h = tag_bbox[3] - tag_bbox[1]
    tag_pad_h = 24   # horizontal padding each side (matches brand: padding 12px 24px)
    tag_pad_v = 13   # vertical padding each side
    tag_w = text_w + tag_pad_h * 2
    tag_h = text_h + tag_pad_v * 2
    tag_x = W - pad - tag_w
    tag_mid = logo_y + 32
    _rrect(draw, [tag_x, tag_mid - tag_h // 2, tag_x + tag_w, tag_mid + tag_h // 2], r=14, outline=accent, width=2)
    draw.text((tag_x + tag_pad_h - tag_bbox[0], tag_mid - tag_h // 2 + tag_pad_v - tag_bbox[1]), sport, font=tag_f, fill=accent)

    # Date — right-aligned below the sport tag pill
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), tag_mid + tag_h // 2 + 12), date_label, font=date_f, fill=NIGHT["muted"])

    # Cover kicker — use exact kicker string from brand template
    theme = pick.get("coverTheme", "Daily Pick")
    theme_data = COVER_THEMES.get(theme, COVER_THEMES["Daily Pick"])
    kicker_f = _f("SpaceMono-Bold.ttf", 26)
    kicker_y = pad + 108
    draw.text((pad, kicker_y), f"// {theme_data['kicker']}", font=kicker_f, fill=accent)

    # Giant headline — line 1 white, line 2 accent, line 3 white
    lines = theme_data["lines"]
    headline_f = _f("Archivo-Black.ttf", 172)
    line_h = 155
    hy = kicker_y + 70
    for i, line in enumerate(lines):
        if not line:
            continue
        col = accent if i == 1 else "#EAF7EF"
        draw.text((pad, hy), line, font=headline_f, fill=col)
        hy += line_h

    # Subline — word-wrap, floats below the headline
    sub_f = _f("SpaceGrotesk-Medium.ttf", 34)
    sub_y = H - pad - 200
    sub_text = "One selection. One slide. Locked in below."
    sub_lines = _wrap(draw, sub_text, sub_f, W - 2 * pad)
    for sub_line in sub_lines:
        draw.text((pad, sub_y), sub_line, font=sub_f, fill=NIGHT["muted"])
        sub_y += int(34 * 1.4)

    # SWIPE → — fixed position above the footer rule
    swipe_f = _f("SpaceMono-Bold.ttf", 26)
    swipe_y = H - pad - 110
    draw.text((pad, swipe_y), "SWIPE →", font=swipe_f, fill=accent)

    # Bottom rule + footer
    rule_y = H - pad - 58
    draw.line([(pad, rule_y), (W - pad, rule_y)], fill=NIGHT["dimmer"], width=1)

    handle_f = _f("SpaceGrotesk-Medium.ttf", 24)
    draw.text((pad, rule_y + 12), "@puntmatenz", font=handle_f, fill="#EAF7EF")
    r18_f = _f("SpaceMono-Regular.ttf", 22)
    r18_text = "R18 · Gamble responsibly · 0800 654 655"
    r18_bb = draw.textbbox((0, 0), r18_text, font=r18_f)
    draw.text((W - pad - (r18_bb[2] - r18_bb[0]), rule_y + 14), r18_text, font=r18_f, fill=NIGHT["muted"])
    disc_f = _f("SpaceMono-Regular.ttf", 17)
    disc_text = "Odds indicative only. Confirm with your betting provider."
    disc_bb = draw.textbbox((0, 0), disc_text, font=disc_f)
    draw.text(((W - (disc_bb[2] - disc_bb[0])) // 2, rule_y + 38), disc_text, font=disc_f, fill="#888888")

    return img


def _night_slide2_tip(pick):
    """Betslip Night — The Tip slide: betslip card."""
    palette = NIGHT_ACCENTS.get(pick.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent = palette["accent"]
    accent_dim = palette["accent_dim"]

    img = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))

    pad = 80

    # Header
    header_f = _f("SpaceMono-Bold.ttf", 26)
    draw.text((pad, pad), "// THE PICK", font=header_f, fill=accent)

    market_f = _f("SpaceMono-Regular.ttf", 24)
    draw.text((pad, pad + 50), pick.get("market", "Head to Head").upper(), font=market_f, fill=NIGHT["muted"])

    # Date — top-right, aligned with "// THE PICK" header
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), pad + 7), date_label, font=date_f, fill=NIGHT["muted"])

    # Betslip card
    card_top = pad + 110
    card_bot = H - pad - 30
    _rrect(draw, [pad, card_top, W - pad, card_bot], r=32,
           fill=NIGHT["surface"], outline=accent_dim, width=2)

    # Betslip header bar
    dot_x, dot_y = pad + 44, card_top + 50
    draw.ellipse([dot_x, dot_y, dot_x + 12, dot_y + 12], fill=accent)
    bs_f = _f("SpaceMono-Bold.ttf", 24)
    draw.text((dot_x + 24, dot_y - 6), "BETSLIP", font=bs_f, fill=accent)

    leg_f = _f("SpaceMono-Regular.ttf", 22)
    leg_tb = draw.textbbox((0, 0), "1 LEG", font=leg_f)
    draw.text((W - pad - (leg_tb[2] - leg_tb[0]) - 44, card_top + 42), "1 LEG", font=leg_f, fill=NIGHT["muted"])

    # Match
    lbl_f = _f("SpaceMono-Regular.ttf", 20)
    val_f  = _f("SpaceGrotesk-Bold.ttf", 46)
    sel_f  = _f("SpaceGrotesk-Bold.ttf", 80)
    # Market pill uses Space Grotesk (not mono) — matches brand guide
    mkt_f  = _f("SpaceGrotesk-Medium.ttf", 26)

    inner_x = pad + 44
    max_inner_w = W - 2 * pad - 88  # card inner width

    cy = card_top + 120
    draw.text((inner_x, cy), "MATCH", font=lbl_f, fill=NIGHT["muted"])
    cy += 32
    draw.text((inner_x, cy), pick.get("match", ""), font=val_f, fill=NIGHT["text"])

    cy += 70
    draw.text((inner_x, cy), "SELECTION", font=lbl_f, fill=NIGHT["muted"])
    cy += 30
    selection = pick.get("selection", "")
    # Wrap selection at spaces AND hyphens (handles long player names)
    sel_words = re.split(r'(?<=-)(?=\S)|(?<=\s)', selection)
    sel_lines, cur = [], []
    for tok in sel_words:
        test = "".join(cur + [tok])
        bb = draw.textbbox((0, 0), test, font=sel_f)
        if (bb[2] - bb[0]) > max_inner_w and cur:
            sel_lines.append("".join(cur).rstrip())
            cur = [tok.lstrip()]
        else:
            cur.append(tok)
    if cur:
        sel_lines.append("".join(cur).rstrip())
    sel_lh = 88  # line height for 80px font
    for sel_line in sel_lines:
        draw.text((inner_x, cy), sel_line, font=sel_f, fill=NIGHT["text"])
        cy += sel_lh

    # Market pill — positioned dynamically after selection
    cy += 20
    pill_text = pick.get("market", "Head to Head")
    pill_bbox = draw.textbbox((0, 0), pill_text, font=mkt_f)
    pill_tw = pill_bbox[2] - pill_bbox[0]
    pill_th = pill_bbox[3] - pill_bbox[1]
    pill_ph, pill_pv = 20, 10
    pill_w = pill_tw + pill_ph * 2
    pill_h = pill_th + pill_pv * 2
    _rrect(draw, [inner_x, cy, inner_x + pill_w, cy + pill_h], r=14,
           outline=accent_dim, width=2)
    draw.text((inner_x + pill_ph - pill_bbox[0], cy + pill_pv - pill_bbox[1]), pill_text, font=mkt_f, fill=accent)

    # Ticket tear divider
    div_y = card_bot - 220
    circle_r = 18
    draw.ellipse(
        [pad - circle_r, div_y - circle_r, pad + circle_r, div_y + circle_r],
        fill=NIGHT["bg"]
    )
    draw.ellipse(
        [W - pad - circle_r, div_y - circle_r, W - pad + circle_r, div_y + circle_r],
        fill=NIGHT["bg"]
    )
    # Dashed line
    x = pad + 20
    while x < W - pad - 20:
        draw.line([(x, div_y), (x + 18, div_y)], fill=NIGHT["dimmer"], width=2)
        x += 28

    # ── Bottom section: DECIMAL ODDS (left) | big odds number (right), bottom-aligned ──
    inner_x = pad + 44
    section_bottom = card_bot - 56  # bottom of usable space inside card — extra breathing room

    # Measure left column height (DECIMAL ODDS label + oddsNote)
    lbl_h = draw.textbbox((0, 0), "DECIMAL ODDS", font=lbl_f)[3]
    odds_note = pick.get("oddsNote", pick.get("insight", ""))
    note_f = _f("SpaceGrotesk-Medium.ttf", 24)
    note_h = draw.textbbox((0, 0), odds_note or " ", font=note_f)[3]
    left_col_h = lbl_h + 8 + note_h

    # Measure right odds number height
    odds_f = _f("SpaceMono-Bold.ttf", 112)
    odds_str = str(pick.get("odds", "2.00"))
    odds_bbox = draw.textbbox((0, 0), odds_str, font=odds_f)
    odds_h = odds_bbox[3] - odds_bbox[1]

    # Bottom-align both columns
    lbl_y = section_bottom - left_col_h
    note_y = lbl_y + lbl_h + 8
    odds_y = section_bottom - odds_h

    draw.text((inner_x, lbl_y), "DECIMAL ODDS", font=lbl_f, fill=NIGHT["muted"])
    if odds_note:
        draw.text((inner_x, note_y), odds_note, font=note_f, fill=NIGHT["muted"])

    odds_x = W - pad - (odds_bbox[2] - odds_bbox[0]) - 28
    draw.text((odds_x, odds_y), odds_str, font=odds_f, fill=accent)

    # ── Footer outside card: insight | R18 ──
    footer_y = card_bot + 18
    insight = pick.get("insight", "")
    if insight:
        insight_f = _f("SpaceGrotesk-Medium.ttf", 23)
        draw.text((pad, footer_y), insight, font=insight_f, fill=NIGHT["muted"])
    r18_f = _f("SpaceMono-Regular.ttf", 23)
    r18_w = draw.textbbox((0, 0), "R18", font=r18_f)[2]
    draw.text((W - pad - r18_w, footer_y), "R18", font=r18_f, fill=NIGHT["muted"])
    disc_f = _f("SpaceMono-Regular.ttf", 17)
    disc_text = "Odds indicative only. Confirm with your betting provider."
    disc_bb = draw.textbbox((0, 0), disc_text, font=disc_f)
    draw.text(((W - (disc_bb[2] - disc_bb[0])) // 2, footer_y + 30), disc_text, font=disc_f, fill="#888888")

    return img


def _night_slide3_breakdown(pick):
    """Betslip Night — The Breakdown slide: analysis + confidence + CTA."""
    palette = NIGHT_ACCENTS.get(pick.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent = palette["accent"]
    accent_dim = palette["accent_dim"]

    img = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))
    _draw_grid(draw)

    pad = 80

    # Header
    header_f = _f("SpaceMono-Bold.ttf", 26)
    draw.text((pad, pad), "// THE BREAKDOWN", font=header_f, fill=accent)

    # CONFIDENCE LEVEL — right-aligned header (HIGH / MEDIUM / LOW)
    mono_sm_hdr = _f("SpaceMono-Regular.ttf", 22)
    confidence_hdr = int(pick.get("confidence", 3))
    conf_level = CONFIDENCE_LEVEL.get(confidence_hdr, "MEDIUM")
    conf_label_text = f"CONFIDENCE: {conf_level}"
    conf_label_bb = draw.textbbox((0, 0), conf_label_text, font=mono_sm_hdr)
    draw.text((W - pad - (conf_label_bb[2] - conf_label_bb[0]), pad + 7), conf_label_text, font=mono_sm_hdr, fill=accent)

    # Date — right-aligned below confidence label
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), pad + 33), date_label, font=date_f, fill=NIGHT["muted"])

    # Risk chips (split riskTagline on · or .)
    chip_f = _f("SpaceMono-Regular.ttf", 22)
    raw_chips = pick.get("riskTagline", "Low risk · Steady returns · Long game")
    chips = [c.strip().upper() for c in re.split(r"[·.]", raw_chips) if c.strip()]
    cx = pad
    cy = pad + 76
    for chip in chips:
        if not chip:
            continue
        cb = draw.textbbox((0, 0), chip, font=chip_f)
        cw = (cb[2] - cb[0]) + 40
        if cx + cw > W - pad:
            break
        _rrect(draw, [cx, cy, cx + cw, cy + 44], r=14, outline=accent_dim, width=2)
        ch = cb[3] - cb[1]
        draw.text((cx + 20 - cb[0], cy + (44 - ch) // 2 - cb[1]), chip, font=chip_f, fill=accent)
        cx += cw + 14

    # ── 3. Card ──
    card_x1, card_x2 = pad, W - pad
    card_top = cy + 80
    ip = 48  # inner padding
    inner_x = card_x1 + ip

    competition = pick.get("competition", pick.get("sport_label", ""))
    matchup     = pick.get("match", "")
    selection   = pick.get("selection", "")
    odds_str    = str(pick.get("odds", ""))
    sport_tag   = pick.get("sport_label", "")

    # Card height: top_pad + competition(30) + gap(8) + matchup(54) + gap(30) + divider(1) + gap(28) + selection(68) + gap(14) + odds_row(48) + bot_pad
    card_h = ip + 30 + 8 + 54 + 30 + 1 + 28 + 68 + 14 + 48 + ip
    card_bot = card_top + card_h
    _rrect(draw, [card_x1, card_top, card_x2, card_bot], r=28,
           fill=NIGHT["surface"], outline=accent_dim, width=2)

    mono_bold = _f("SpaceMono-Bold.ttf", 20)
    mono_sm   = _f("SpaceMono-Regular.ttf", 22)
    match_f   = _f("SpaceGrotesk-Bold.ttf", 42)
    sel_f     = _f("SpaceGrotesk-Bold.ttf", 56)
    odds_f    = _f("SpaceMono-Bold.ttf", 44)

    # Competition label (top-left) + sport pill (top-right)
    iy = card_top + ip
    draw.text((inner_x, iy), competition, font=mono_sm, fill=NIGHT["muted"])
    tag_bb = draw.textbbox((0, 0), sport_tag, font=mono_bold)
    tag_tw = tag_bb[2] - tag_bb[0]
    tag_th = tag_bb[3] - tag_bb[1]
    tag_ph, tag_pv = 18, 10
    tag_w  = tag_tw + tag_ph * 2
    tag_h  = tag_th + tag_pv * 2
    tag_x1 = card_x2 - ip - tag_w
    _rrect(draw, [tag_x1, iy, tag_x1 + tag_w, iy + tag_h], r=14, outline=accent, width=2)
    draw.text((tag_x1 + tag_ph - tag_bb[0], iy + tag_pv - tag_bb[1]), sport_tag, font=mono_bold, fill=accent)

    # Matchup
    iy += 30 + 8
    draw.text((inner_x, iy), matchup, font=match_f, fill=NIGHT["text"])

    # Divider
    div_y = iy + 54 + 30
    draw.line([(inner_x, div_y), (card_x2 - ip, div_y)], fill=NIGHT["dimmer"], width=1)

    # Selection
    sel_y = div_y + 28
    draw.text((inner_x, sel_y), selection, font=sel_f, fill=NIGHT["text"])

    # Odds + confidence dots inline (template: display:flex; align-items:center; gap:20px)
    row_y = sel_y + 68 + 14
    confidence = int(pick.get("confidence", 3))
    draw.text((inner_x, row_y), odds_str, font=odds_f, fill=accent)
    obb = draw.textbbox((0, 0), odds_str, font=odds_f)
    dot_x = inner_x + (obb[2] - obb[0]) + 20
    dot_sz  = 24
    dot_top = row_y + (48 - dot_sz) // 2
    for i in range(5):
        fill = accent if i < confidence else NIGHT["dimmer"]
        draw.ellipse([dot_x, dot_top, dot_x + dot_sz, dot_top + dot_sz], fill=fill)
        dot_x += dot_sz + 12

    # ── 4. THE READ section (below card, flex:1 in template) ──
    analysis_f  = _f("SpaceGrotesk-Medium.ttf", 33)
    follow_f    = _f("SpaceGrotesk-Bold.ttf", 40)
    edge_f      = _f("SpaceMono-Bold.ttf", 26)
    comp_f2     = _f("SpaceGrotesk-Medium.ttf", 20)

    read_y = card_bot + 36
    draw.text((pad, read_y), "THE READ", font=mono_sm, fill=NIGHT["muted"])

    analysis = pick.get("analysis", "")
    words = analysis.split()
    lines_out, line = [], []
    max_w = W - 2 * pad
    for w in words:
        test = " ".join(line + [w])
        bb = draw.textbbox((0, 0), test, font=analysis_f)
        if (bb[2] - bb[0]) > max_w and line:
            lines_out.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines_out.append(" ".join(line))

    ay = read_y + 38
    lh = int(33 * 1.45)  # ~48px
    footer_reserve = H - pad - 155
    for txt in lines_out:
        if ay + lh > footer_reserve:
            break
        draw.text((pad, ay), txt, font=analysis_f, fill="#C7D6CE")
        ay += lh

    # ── 5. Footer: divider -> CTA row -> compliance (fixed from bottom up) ──
    comp_lh = 26
    comp2_y = H - pad - comp_lh          # second compliance line
    comp1_y = comp2_y - comp_lh - 4     # first compliance line
    draw.text((pad, comp1_y), "R18 · Think of the odds, not the outcome. Gamble responsibly", font=comp_f2, fill=NIGHT["muted"])
    draw.text((pad, comp2_y), "· 0800 654 655 · gamblinghelpline.co.nz", font=comp_f2, fill=NIGHT["muted"])
    disc_f = _f("SpaceGrotesk-Medium.ttf", 17)
    disc_text = "Odds indicative only. Confirm with your betting provider."
    disc_bb = draw.textbbox((0, 0), disc_text, font=disc_f)
    draw.text(((W - (disc_bb[2] - disc_bb[0])) // 2, comp2_y + comp_lh + 2), disc_text, font=disc_f, fill="#888888")

    cta_sz = 56
    cta_y  = comp1_y - 28 - cta_sz

    # Brand icon badge
    cta_logo = _load_logo(cta_sz)
    if cta_logo:
        img.paste(cta_logo, _sp((pad, cta_y)), cta_logo)
    else:
        draw.ellipse([pad, cta_y, pad + cta_sz, cta_y + cta_sz], fill=accent)
        _draw_value_arrow(draw, pad + cta_sz // 2, cta_y + cta_sz // 2, cta_sz - 10, "#0B0F0D")

    # "Follow @puntmatenz"
    handle = pick.get("handle", "@puntmatenz")
    draw.text((pad + cta_sz + 18, cta_y + (cta_sz - 44) // 2),
              f"Follow {handle}", font=follow_f, fill=NIGHT["text"])

    # "DAILY EDGE ->" right-aligned
    edge_text = "DAILY EDGE →"
    ebb = draw.textbbox((0, 0), edge_text, font=edge_f)
    draw.text((W - pad - (ebb[2] - ebb[0]), cta_y + 14), edge_text, font=edge_f, fill=accent)

    # Divider above CTA
    draw.line([(pad, cta_y - 24), (W - pad, cta_y - 24)], fill=NIGHT["dimmer"], width=1)

    return img


# ── Slide generators — Matchday Print ────────────────────────────────────────

def _print_slide1_cover(pick):
    """Matchday Print — Cover slide. Anton for big headlines, Barlow Condensed for kickers."""
    img = Image.new("RGB", (W * S, H * S), PRINT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))

    pad = 72

    # Red top bar
    draw.rectangle([0, 0, W, 100], fill=PRINT["red"])
    wm_f = _f("Archivo-Black.ttf", 36)
    draw.text((pad, 30), "PUNTMATE", font=wm_f, fill=PRINT["yellow"])
    sport_f = _f("BarlowCondensed-Bold.ttf", 30)
    sport = pick.get("sport_label", "SPORT")
    sport_bb = draw.textbbox((0, 0), sport, font=sport_f)
    sport_w = sport_bb[2] - sport_bb[0]
    draw.text((W - pad - sport_w, 33), sport, font=sport_f, fill=PRINT["bg"])

    # Date — top-right, just below the red top bar
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), 108), date_label, font=date_f, fill=PRINT["muted"])

    # Kicker — Barlow Condensed
    kicker_f = _f("BarlowCondensed-SemiBold.ttf", 30)
    theme = pick.get("coverTheme", "Daily Pick")
    draw.text((pad, 130), f"// {theme.upper()}", font=kicker_f, fill=PRINT["red"])

    # Tier pill — right-aligned, same row as kicker (INVESTOR / PUNTER)
    tier = pick.get("tier", "PUNTER").upper()
    tier_f = _f("SpaceMono-Bold.ttf", 22)
    tier_bb = draw.textbbox((0, 0), tier, font=tier_f)
    tier_tw = tier_bb[2] - tier_bb[0]
    tier_th = tier_bb[3] - tier_bb[1]
    tier_ph, tier_pv = 20, 8
    tier_w = tier_tw + tier_ph * 2
    tier_h = tier_th + tier_pv * 2
    tier_x = W - pad - tier_w
    _rrect(draw, [tier_x, 130, tier_x + tier_w, 130 + tier_h], r=10,
           fill=PRINT["ink"])
    draw.text((tier_x + tier_ph - tier_bb[0], 130 + tier_pv - tier_bb[1]),
              tier, font=tier_f, fill=PRINT["yellow"])

    # Giant headline — Anton (proper tabloid stacked)
    lines = COVER_HEADLINES.get(theme, ("BEST", "VALUE", "BET."))
    headline_f = _f("Anton-Regular.ttf", 188)
    hy = 185
    for i, line in enumerate(lines):
        if not line:
            continue
        col = PRINT["red"] if i == 1 else PRINT["ink"]
        draw.text((pad, hy), line, font=headline_f, fill=col)
        hy += 168

    # Subline — Barlow Condensed
    sub_f = _f("BarlowCondensed-SemiBold.ttf", 38)
    draw.text((pad, hy + 30), "ONE SELECTION. ONE SLIDE.", font=sub_f, fill=PRINT["muted"])
    draw.text((pad, hy + 76), "LOCKED IN BELOW.", font=sub_f, fill=PRINT["muted"])

    # Yellow swipe strip
    strip_y = H - 140
    draw.rectangle([0, strip_y, W, strip_y + 100], fill=PRINT["yellow"])
    swipe_f = _f("BarlowCondensed-Bold.ttf", 36)
    draw.text((pad, strip_y + 30), "SWIPE  →  @PUNTMATENZ", font=swipe_f, fill=PRINT["ink"])

    # Compliance
    comp_f = _f("BarlowCondensed-SemiBold.ttf", 22)
    draw.text((pad, H - 38), "R18 · GAMBLE RESPONSIBLY · 0800 654 655", font=comp_f, fill=PRINT["muted"])
    disc_f = _f("BarlowCondensed-SemiBold.ttf", 16)
    draw.text((pad, H - 18), "Odds indicative only. Confirm with your betting provider.", font=disc_f, fill=PRINT["muted"])

    return img


def _print_slide2_tip(pick):
    """Matchday Print — The Tip slide."""
    img = Image.new("RGB", (W * S, H * S), PRINT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))

    pad = 72

    # Red top bar
    draw.rectangle([0, 0, W, 100], fill=PRINT["red"])
    wm_f = _f("Archivo-Black.ttf", 36)
    draw.text((pad, 30), "PUNTMATE", font=wm_f, fill=PRINT["yellow"])

    # THE PICK kicker — Barlow Condensed
    kicker_f = _f("BarlowCondensed-Bold.ttf", 32)
    draw.text((pad, 120), "// THE PICK", font=kicker_f, fill=PRINT["red"])

    # Date — right-aligned, same row as kicker
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), 120), date_label, font=date_f, fill=PRINT["muted"])

    # MATCH — Barlow Condensed
    lbl_f = _f("BarlowCondensed-SemiBold.ttf", 26)
    draw.text((pad, 185), "MATCH", font=lbl_f, fill=PRINT["muted"])
    match_f = _f("BarlowCondensed-Bold.ttf", 56)
    draw.text((pad, 215), pick.get("match", ""), font=match_f, fill=PRINT["ink"])

    # Red rule
    draw.rectangle([pad, 285, W - pad, 292], fill=PRINT["red"])

    # Giant selection — Anton, wrap to 2 lines, dynamic cy
    sel_f = _f("Anton-Regular.ttf", 128)
    selection = pick.get("selection", "")
    sel_words = re.split(r'(?<=-)(?=\S)|(?<=\s)', selection)
    sel_lines_out, sel_cur = [], []
    max_sel_w = W - 2 * pad
    for tok in sel_words:
        test = "".join(sel_cur + [tok])
        bb = draw.textbbox((0, 0), test, font=sel_f)
        if (bb[2] - bb[0]) > max_sel_w and sel_cur:
            sel_lines_out.append("".join(sel_cur).rstrip())
            sel_cur = [tok.lstrip()]
        else:
            sel_cur.append(tok)
    if sel_cur:
        sel_lines_out.append("".join(sel_cur).rstrip())
    cy = 308
    for sel_line in sel_lines_out[:3]:
        draw.text((pad, cy), sel_line, font=sel_f, fill=PRINT["ink"])
        cy += 120
    cy += 16

    # Market pill — correct width = text width + padding (not x2 of bbox)
    mkt_f = _f("BarlowCondensed-Bold.ttf", 28)
    mkt_txt = pick.get("market", "HEAD TO HEAD").upper()
    mkt_bb = draw.textbbox((0, 0), mkt_txt, font=mkt_f)
    mkt_w = (mkt_bb[2] - mkt_bb[0]) + 48
    _rrect(draw, [pad, cy, pad + mkt_w, cy + 48], r=14, fill=PRINT["red"])
    draw.text((pad + 24 - mkt_bb[0], cy + 10 - mkt_bb[1]), mkt_txt, font=mkt_f, fill=PRINT["bg"])
    cy += 64

    # Confidence dots (filled=red, empty=cream with ink border)
    confidence = int(pick.get("confidence", 3))
    dot_sz, dot_gap = 22, 10
    dot_x = pad
    for i in range(5):
        draw.ellipse([dot_x, cy, dot_x + dot_sz, cy + dot_sz],
                     fill=PRINT["red"] if i < confidence else PRINT["bg"],
                     outline=PRINT["ink"], width=2)
        dot_x += dot_sz + dot_gap
    cy += dot_sz + 28

    # Odds — Anton for the number, dynamic y
    odds_lbl_f = _f("BarlowCondensed-SemiBold.ttf", 26)
    draw.text((pad, cy), "DECIMAL ODDS", font=odds_lbl_f, fill=PRINT["muted"])
    cy += 32
    odds_f = _f("Anton-Regular.ttf", 150)
    draw.text((pad, cy), str(pick.get("odds", "")), font=odds_f, fill=PRINT["red"])
    cy += 160

    # Insight line
    insight = pick.get("insight", "")
    if insight:
        insight_f = _f("BarlowCondensed-SemiBold.ttf", 32)
        draw.text((pad, cy), insight, font=insight_f, fill=PRINT["muted"])

    # Yellow bottom strip
    strip_y = H - 140
    draw.rectangle([0, strip_y, W, strip_y + 100], fill=PRINT["yellow"])
    swipe_f = _f("BarlowCondensed-Bold.ttf", 34)
    draw.text((pad, strip_y + 32), "SWIPE  →  SEE THE BREAKDOWN", font=swipe_f, fill=PRINT["ink"])

    comp_f = _f("BarlowCondensed-SemiBold.ttf", 22)
    draw.text((pad, H - 38), "R18 · GAMBLE RESPONSIBLY · 0800 654 655", font=comp_f, fill=PRINT["muted"])
    disc_f = _f("BarlowCondensed-SemiBold.ttf", 16)
    draw.text((pad, H - 18), "Odds indicative only. Confirm with your betting provider.", font=disc_f, fill=PRINT["muted"])

    return img


def _print_slide3_breakdown(pick):
    """Matchday Print — The Verdict (template-accurate: dark header, WHY WE'RE ON, analysis, red footer)."""
    img = Image.new("RGB", (W * S, H * S), PRINT["bg"])
    draw = ScaledDraw(ImageDraw.Draw(img))
    pad = 80

    f_bc_700_44 = _f("BarlowCondensed-Bold.ttf", 44)
    f_anton_38  = _f("Anton-Regular.ttf", 38)
    f_bc_700_26 = _f("BarlowCondensed-Bold.ttf", 26)
    f_anton_120 = _f("Anton-Regular.ttf", 120)
    f_bc_600_28 = _f("BarlowCondensed-SemiBold.ttf", 28)
    f_anton_60  = _f("Anton-Regular.ttf", 60)
    f_bc_500_40 = _f("BarlowCondensed-SemiBold.ttf", 40)
    f_mono_20   = _f("SpaceMono-Regular.ttf", 20)

    # Dark header bar
    header_h = 100
    draw.rectangle([0, 0, W, header_h], fill=PRINT["ink"])
    draw.text((pad, 28), "THE VERDICT", font=f_bc_700_44, fill="#F4EEE2")
    confidence = int(pick.get("confidence", 3))
    conf_display = pick.get("confidenceLabel", CONFIDENCE_RISK.get(confidence, "MODERATE"))
    risk_text = f"{conf_display} RISK"
    rb = draw.textbbox((0, 0), risk_text, font=f_anton_38)
    draw.text((W - pad - (rb[2] - rb[0]), 30), risk_text, font=f_anton_38, fill=PRINT["yellow"])

    # Date — right-aligned, just below the dark header bar
    _now = datetime.now(timezone.utc)
    date_label = f"{_now.strftime('%a').upper()} {int(_now.strftime('%d'))} {_now.strftime('%b').upper()}"
    date_f = _f("SpaceMono-Regular.ttf", 22)
    date_bb = draw.textbbox((0, 0), date_label, font=date_f)
    draw.text((W - pad - (date_bb[2] - date_bb[0]), header_h + 8), date_label, font=date_f, fill=PRINT["muted"])

    # Body
    body_y = header_h + 64

    # Risk chips (dark bg, cream text — Barlow Condensed Bold)
    raw_chips = pick.get("riskTagline", "Low risk · Steady returns · Long game")
    chips = [c.strip().upper() for c in re.split(r"[·.]", raw_chips) if c.strip()]
    cx = pad
    cy = body_y
    for chip in chips:
        cb = draw.textbbox((0, 0), chip, font=f_bc_700_26)
        cw = (cb[2] - cb[0]) + 40
        if cx + cw > W - pad:
            break
        draw.rectangle([cx, cy, cx + cw, cy + 44], fill=PRINT["ink"])
        draw.text((cx + 20 - cb[0], cy + 6 - cb[1]), chip, font=f_bc_700_26, fill="#F4EEE2")
        cx += cw + 8

    # "WHY WE'RE / ON" — two stacked lines so Anton 120 never overflows the card
    why_y = cy + 44 + 40
    draw.text((pad, why_y), "WHY WE'RE", font=f_anton_120, fill=PRINT["ink"])
    on_y = why_y + int(120 * 0.84)
    draw.text((pad, on_y), "ON", font=f_anton_120, fill=PRINT["red"])

    # Bordered section: competition | selectionShort + odds | confidence dots
    border_y = on_y + int(120 * 0.84) + 24
    draw.line([(pad, border_y), (W - pad, border_y)], fill=PRINT["ink"], width=4)

    competition   = pick.get("competition", pick.get("sport_label", ""))
    matchup_caps  = pick.get("match", "").upper()
    selection_s   = pick.get("selectionShort", pick.get("selection", "")).upper()
    odds_str      = str(pick.get("odds", ""))

    comp_text = f"{competition} · {matchup_caps}" if competition else matchup_caps
    comp_y = border_y + 28
    draw.text((pad, comp_y), comp_text, font=f_bc_600_28, fill=PRINT["muted"])

    sel_y = comp_y + 36
    # Selection — left aligned only (no inline odds to prevent overflow)
    draw.text((pad, sel_y), selection_s, font=f_anton_60, fill=PRINT["ink"])

    # Odds — right aligned to same edge as dots
    ob = draw.textbbox((0, 0), odds_str, font=f_anton_60)
    draw.text((W - pad - (ob[2] - ob[0]), sel_y), odds_str, font=f_anton_60, fill=PRINT["red"])

    # Confidence dots — right aligned, vertically below odds
    dot_sz = 28
    dot_gap = 12
    dots_w = 5 * dot_sz + 4 * dot_gap
    dot_x = W - pad - dots_w
    dot_mid = sel_y + 52
    for i in range(5):
        is_filled = i < confidence
        draw.ellipse([dot_x, dot_mid, dot_x + dot_sz, dot_mid + dot_sz],
                     fill=PRINT["red"] if is_filled else PRINT["bg"],
                     outline=PRINT["ink"], width=3)
        dot_x += dot_sz + dot_gap

    border_bot = sel_y + 92
    draw.line([(pad, border_bot), (W - pad, border_bot)], fill=PRINT["ink"], width=4)

    # Analysis — Barlow Condensed 500 40px, line-height 1.25
    red_footer_h = 90
    analysis = pick.get("analysis", "")
    words = analysis.split()
    lines_out, line = [], []
    max_w = W - 2 * pad
    for w in words:
        test = " ".join(line + [w])
        bb = draw.textbbox((0, 0), test, font=f_bc_500_40)
        if (bb[2] - bb[0]) > max_w and line:
            lines_out.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines_out.append(" ".join(line))

    ay = border_bot + 40
    lh = int(40 * 1.25)
    for txt in lines_out:
        if ay + lh > H - red_footer_h - 10:
            break
        draw.text((pad, ay), txt, font=f_bc_500_40, fill=PRINT["ink"])
        ay += lh

    # Red footer bar
    footer_y = H - red_footer_h
    draw.rectangle([0, footer_y, W, H], fill=PRINT["red"])
    handle = pick.get("handle", "@puntmatenz")
    draw.text((pad, footer_y + 28), f"FOLLOW {handle.upper()}", font=f_mono_20, fill="#F4EEE2")
    r18 = "R18 · Gamble responsibly · 0800 654 655"
    r18_bb = draw.textbbox((0, 0), r18, font=f_mono_20)
    draw.text((W - pad - (r18_bb[2] - r18_bb[0]), footer_y + 28), r18, font=f_mono_20, fill="#F4EEE2")
    disc_f = _f("SpaceMono-Regular.ttf", 14)
    disc_text = "Odds indicative only. Confirm with your betting provider."
    disc_bb = draw.textbbox((0, 0), disc_text, font=disc_f)
    draw.text(((W - (disc_bb[2] - disc_bb[0])) // 2, footer_y + 56), disc_text, font=disc_f, fill="#E0D0BC")

    return img


# ── Multi carousel (Betslip Night look, 3 slides) ────────────────────────────

def _wrap(draw, text, font, max_w):
    """Simple word-wrap: returns list of lines that fit within max_w pixels."""
    words = text.split()
    lines_out, line = [], []
    for w in words:
        test = " ".join(line + [w])
        bb = draw.textbbox((0, 0), test, font=font)
        if (bb[2] - bb[0]) > max_w and line:
            lines_out.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines_out.append(" ".join(line))
    return lines_out


def generate_multi_images(legs, meta, output_dir):
    """
    Generate a 3-slide Multi carousel.
    legs: list of dicts with keys: match, selection, market, odds
    meta: dict with keys: palette, coverKicker, analysis, confidence, confidenceLabel,
          riskTagline, handle, multiType, stake
    Returns list of 3 file paths.
    """
    import math as _math
    os.makedirs(output_dir, exist_ok=True)

    palette = NIGHT_ACCENTS.get(meta.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent     = palette["accent"]
    accent_dim = palette["accent_dim"]
    pad = 80

    # Combined odds
    product, valid = 1.0, 0
    for leg in legs:
        try:
            v = float(str(leg.get("odds", "")).replace("$", ""))
            if v > 0:
                product *= v
                valid += 1
        except (ValueError, TypeError):
            pass
    combined_odds = meta.get("combinedOdds", f"${product:.2f}" if valid else "—")

    confidence = int(meta.get("confidence", 3))
    conf_display = meta.get("confidenceLabel", CONFIDENCE_RISK.get(confidence, "MODERATE"))
    handle = meta.get("handle", "@puntmatenz")
    leg_count = len(legs)

    def _header_bar(img, draw, right_text):
        """Draw PUNTMATE wordmark + right_text pill."""
        lkup = _load_lockup(56)
        if lkup:
            img.paste(lkup, _sp((pad, pad)), lkup)
        else:
            _wordmark(draw, pad, pad + 8, 28, accent)
        rf = _f("SpaceMono-Bold.ttf", 22)
        rb = draw.textbbox((0, 0), right_text, font=rf)
        rw = rb[2] + 40
        _rrect(draw, [W - pad - rw, pad + 4, W - pad, pad + 48], r=14, outline=accent, width=2)
        draw.text((W - pad - rw + 20, pad + 14), right_text, font=rf, fill=accent)

    # ── Slide 1: Cover ──
    s1 = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    d1 = ScaledDraw(ImageDraw.Draw(s1))
    _header_bar(s1, d1, f"{leg_count}-LEG")
    kicker_f = _f("SpaceMono-Bold.ttf", 26)
    d1.text((pad, pad + 108), f"// {meta.get('coverKicker', 'MULTI MONDAY')}", font=kicker_f, fill=accent)
    hl_f = _f("Archivo-Black.ttf", 180)
    d1.text((pad, pad + 170), "THE", font=hl_f, fill="#EAF7EF")
    d1.text((pad, pad + 170 + 160), "MULTI.", font=hl_f, fill=accent)
    sub_f = _f("SpaceGrotesk-Medium.ttf", 34)
    d1.text((pad, pad + 170 + 320 + 30),
            f"{leg_count} legs, one slip. Combined at {combined_odds}.", font=sub_f, fill=NIGHT["muted"])
    sw_f = _f("SpaceMono-Bold.ttf", 26)
    d1.text((pad, H - pad - 120), "SWIPE FOR THE LEGS →", font=sw_f, fill=accent)
    d1.line([(pad, H - pad - 55), (W - pad, H - pad - 55)], fill=NIGHT["dimmer"], width=1)
    hf = _f("SpaceGrotesk-Medium.ttf", 24)
    d1.text((pad, H - pad - 38), handle, font=hf, fill="#EAF7EF")
    r18f = _f("SpaceMono-Regular.ttf", 22)
    r18t = "R18 · Gamble responsibly · 0800 654 655"
    r18b = d1.textbbox((0, 0), r18t, font=r18f)
    d1.text((W - pad - (r18b[2] - r18b[0]), H - pad - 38), r18t, font=r18f, fill=NIGHT["muted"])
    disc_f1 = _f("SpaceMono-Regular.ttf", 17)
    disc_text1 = "Odds indicative only. Confirm with your betting provider."
    disc_bb1 = d1.textbbox((0, 0), disc_text1, font=disc_f1)
    d1.text(((W - (disc_bb1[2] - disc_bb1[0])) // 2, H - pad - 14), disc_text1, font=disc_f1, fill="#888888")

    # ── Slide 2: The Legs ──
    s2 = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    d2 = ScaledDraw(ImageDraw.Draw(s2))
    hdr_f = _f("SpaceMono-Bold.ttf", 26)
    d2.text((pad, pad), "// THE LEGS", font=hdr_f, fill=accent)
    cnt_f = _f("SpaceMono-Regular.ttf", 22)
    ct = f"{leg_count} LEGS"
    ctb = d2.textbbox((0, 0), ct, font=cnt_f)
    d2.text((W - pad - (ctb[2] - ctb[0]) - 16, pad + 7), ct, font=cnt_f, fill=NIGHT["muted"])

    # Leg rows
    leg_top = pad + 68
    row_h = 110
    num_f = _f("SpaceMono-Bold.ttf", 30)
    sel_f = _f("SpaceGrotesk-Bold.ttf", 36)
    det_f = _f("SpaceGrotesk-Medium.ttf", 22)
    leg_odds_f = _f("SpaceMono-Bold.ttf", 40)
    for idx, leg in enumerate(legs[:5]):
        ry = leg_top + idx * (row_h + 16)
        _rrect(d2, [pad, ry, W - pad, ry + row_h], r=22, fill=NIGHT["surface"])
        # Number badge — center digit within the 60×60 badge
        badge_x, badge_y, badge_sz = pad + 22, ry + 25, 60
        _rrect(d2, [badge_x, badge_y, badge_x + badge_sz, badge_y + badge_sz], r=16, fill=accent_dim)
        num_str = str(idx + 1)
        nb = d2.textbbox((0, 0), num_str, font=num_f)
        nw, nh = nb[2] - nb[0], nb[3] - nb[1]
        d2.text((badge_x + (badge_sz - nw) // 2 - nb[0], badge_y + (badge_sz - nh) // 2 - nb[1]), num_str, font=num_f, fill=accent)
        # Selection + detail
        sel_txt = leg.get("selection", "")
        det_txt = (leg.get("match", "") + (" · " + leg.get("market", "") if leg.get("market") else "")).strip(" · ")
        d2.text((pad + 100, ry + 16), sel_txt, font=sel_f, fill=NIGHT["text"])
        d2.text((pad + 100, ry + 58), det_txt, font=det_f, fill=NIGHT["muted"])
        # Odds right
        lo = str(leg.get("odds", ""))
        lob = d2.textbbox((0, 0), lo, font=leg_odds_f)
        d2.text((W - pad - (lob[2] - lob[0]) - 22, ry + 30), lo, font=leg_odds_f, fill=accent)

    # Combined odds bar
    bar_top = leg_top + leg_count * (row_h + 16) + 16
    _rrect(d2, [pad, bar_top, W - pad, bar_top + 96], r=24, fill=NIGHT["surface"], outline=accent_dim, width=2)
    lbl_f = _f("SpaceMono-Regular.ttf", 22)
    d2.text((pad + 36, bar_top + 18), "COMBINED ODDS", font=lbl_f, fill=NIGHT["muted"])
    mt = meta.get("multiType", "Multi")
    d2.text((pad + 36, bar_top + 52), f"{leg_count} legs · {mt}", font=_f("SpaceGrotesk-Medium.ttf", 22), fill=NIGHT["muted"])
    co_f = _f("SpaceMono-Bold.ttf", 54)
    cob = d2.textbbox((0, 0), combined_odds, font=co_f)
    co_h_px = cob[3] - cob[1]
    co_vy = bar_top + (96 - co_h_px) // 2 - cob[1]
    d2.text((W - pad - (cob[2] - cob[0]) - 36, co_vy), combined_odds, font=co_f, fill=accent)

    # ── Slide 3: The Breakdown ──
    s3 = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    d3 = ScaledDraw(ImageDraw.Draw(s3))
    d3.text((pad, pad), "// THE BREAKDOWN", font=_f("SpaceMono-Bold.ttf", 26), fill=accent)
    conf_level_multi = CONFIDENCE_LEVEL.get(confidence, "MEDIUM")
    conf_label_multi = f"CONFIDENCE: {conf_level_multi}"
    rtb = d3.textbbox((0, 0), conf_label_multi, font=_f("SpaceMono-Regular.ttf", 22))
    d3.text((W - pad - (rtb[2] - rtb[0]), pad + 7), conf_label_multi, font=_f("SpaceMono-Regular.ttf", 22), fill=accent)

    raw_chips = meta.get("riskTagline", "Higher risk · Bigger return · One to dream on")
    chips3 = [c.strip().upper() for c in re.split(r"[·.]", raw_chips) if c.strip()]
    cx3 = pad
    cy3 = pad + 76
    cf3 = _f("SpaceMono-Regular.ttf", 22)
    for chip in chips3:
        cb = d3.textbbox((0, 0), chip, font=cf3)
        cw = (cb[2] - cb[0]) + 40
        if cx3 + cw > W - pad:
            break
        _rrect(d3, [cx3, cy3, cx3 + cw, cy3 + 44], r=14, outline=accent_dim, width=2)
        ch3 = cb[3] - cb[1]
        d3.text((cx3 + 20 - cb[0], cy3 + (44 - ch3) // 2 - cb[1]), chip, font=cf3, fill=accent)
        cx3 += cw + 14

    # Summary card — left: label + stake return | right column: odds (top) + dots (below)
    # Card height: top_pad(24) + label(28) + gap(8) + stake(44) + bot_pad(24) = 128px min
    # Right col: odds(68) + gap(12) + dots(22) = 102px, fits with top+bot pad(24 each) = 150px
    sc_h = 150
    sc_top = cy3 + 80
    _rrect(d3, [pad, sc_top, W - pad, sc_top + sc_h], r=28, fill=NIGHT["surface"], outline=accent_dim, width=2)

    # Left column
    d3.text((pad + 36, sc_top + 24), f"THE MULTI · {leg_count} LEGS", font=_f("SpaceMono-Regular.ttf", 22), fill=NIGHT["muted"])
    stake = meta.get("stake", "$10")
    try:
        sv = float(str(stake).replace("$", "").replace(",", ""))
        stake_return = f"{stake} returns ${sv * product:.2f}"
    except (ValueError, TypeError):
        stake_return = f"{stake} stake"
    d3.text((pad + 36, sc_top + 62), stake_return, font=_f("SpaceGrotesk-Bold.ttf", 36), fill=NIGHT["text"])

    # Right column: combined odds (top) then confidence dots below — both right-aligned
    co56 = _f("SpaceMono-Bold.ttf", 56)
    cob56 = d3.textbbox((0, 0), combined_odds, font=co56)
    co_w = cob56[2] - cob56[0]
    co_h = cob56[3] - cob56[1]
    right_edge = W - pad - 36
    # Odds: right-aligned, vertically centred in right col (pad 24 top)
    d3.text((right_edge - co_w, sc_top + 24), combined_odds, font=co56, fill=accent)
    # Dots: right-aligned, 12px below the odds baseline
    dot_sz3 = 22
    dot_gap3 = 12
    dots_w3 = 5 * dot_sz3 + 4 * dot_gap3
    dot_x3 = right_edge - dots_w3
    dot_y3 = sc_top + 24 + co_h + 12
    for i in range(5):
        fill3 = accent if i < confidence else NIGHT["dimmer"]
        d3.ellipse([dot_x3, dot_y3, dot_x3 + dot_sz3, dot_y3 + dot_sz3], fill=fill3)
        dot_x3 += dot_sz3 + dot_gap3

    # THE READ
    read_y3 = sc_top + sc_h + 36
    d3.text((pad, read_y3), "THE READ", font=_f("SpaceMono-Regular.ttf", 22), fill=NIGHT["muted"])
    af3 = _f("SpaceGrotesk-Medium.ttf", 33)
    a3_lines = _wrap(d3, meta.get("analysis", ""), af3, W - 2 * pad)
    ay3 = read_y3 + 38
    lh3 = int(33 * 1.45)
    fr3 = H - pad - 155
    for txt in a3_lines:
        if ay3 + lh3 > fr3:
            break
        d3.text((pad, ay3), txt, font=af3, fill="#C7D6CE")
        ay3 += lh3

    # Footer (fixed from bottom up — two compliance lines, then CTA above)
    comp_f3 = _f("SpaceGrotesk-Medium.ttf", 20)
    comp_lh3 = 26
    comp2_y3 = H - pad - comp_lh3
    comp1_y3 = comp2_y3 - comp_lh3 - 4
    d3.text((pad, comp1_y3), "R18 · Think of the odds, not the outcome. Gamble responsibly", font=comp_f3, fill=NIGHT["muted"])
    d3.text((pad, comp2_y3), "· 0800 654 655 · gamblinghelpline.co.nz", font=comp_f3, fill=NIGHT["muted"])
    disc_f3 = _f("SpaceGrotesk-Medium.ttf", 17)
    disc_text3 = "Odds indicative only. Confirm with your betting provider."
    disc_bb3 = d3.textbbox((0, 0), disc_text3, font=disc_f3)
    d3.text(((W - (disc_bb3[2] - disc_bb3[0])) // 2, comp2_y3 + comp_lh3 + 2), disc_text3, font=disc_f3, fill="#888888")
    cta_y3 = comp1_y3 - 28 - 56
    cta_logo3 = _load_logo(56)
    if cta_logo3:
        s3.paste(cta_logo3, _sp((pad, cta_y3)), cta_logo3)
    else:
        d3.ellipse([pad, cta_y3, pad + 56, cta_y3 + 56], fill=accent)
        _draw_value_arrow(d3, pad + 28, cta_y3 + 28, 46, "#0B0F0D")
    d3.text((pad + 74, cta_y3 + 6), f"Follow {handle}", font=_f("SpaceGrotesk-Bold.ttf", 40), fill=NIGHT["text"])
    et3 = "DAILY EDGE →"
    eb3 = d3.textbbox((0, 0), et3, font=_f("SpaceMono-Bold.ttf", 26))
    d3.text((W - pad - (eb3[2] - eb3[0]), cta_y3 + 14), et3, font=_f("SpaceMono-Bold.ttf", 26), fill=accent)
    d3.line([(pad, cta_y3 - 24), (W - pad, cta_y3 - 24)], fill=NIGHT["dimmer"], width=1)

    # Save all three (downscale via LANCZOS for crisp output)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paths = []
    for slide, label in zip([s1, s2, s3], ["1_cover", "2_legs", "3_breakdown"]):
        path = f"{output_dir}/{date_str}_multi_{label}.png"
        _save(slide, path)
        paths.append(path)
    return paths


# ── Results carousel (Betslip Night look, 2 slides) ──────────────────────────

def generate_results_images(results, meta, output_dir):
    """
    Generate a 2-slide Results carousel.
    results: list of dicts with keys: match, selection, odds, result ("WON"/"LOST"/"VOID")
    meta: dict with keys: palette, period, summary, handle
    Returns list of 2 file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    palette = NIGHT_ACCENTS.get(meta.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent     = palette["accent"]
    accent_dim = palette["accent_dim"]
    pad = 80
    LOSS = "#FF5C5C"
    MUTE = NIGHT["muted"]

    # Calculate stats
    wins = losses = voids = 0
    profit = 0.0
    best = 0.0
    rows = []
    for r in results[:7]:
        result = r.get("result", "WON").upper()
        try:
            o = float(str(r.get("odds", "0")).replace("$", ""))
        except (ValueError, TypeError):
            o = 0.0
        if result == "WON":
            wins += 1
            profit += (o - 1)
            if o - 1 > best:
                best = o - 1
            tag_color, tag_bg = accent, accent_dim
            odds_color = accent
        elif result == "LOST":
            losses += 1
            profit -= 1.0
            tag_color, tag_bg = LOSS, "#5C1A1A"
            odds_color = MUTE
        else:
            voids += 1
            tag_color, tag_bg = MUTE, NIGHT["surface"]
            odds_color = MUTE
        rows.append({**r, "result": result, "tag_color": tag_color, "tag_bg": tag_bg, "odds_color": odds_color})

    settled = wins + losses
    strike_rate = round((wins / settled) * 100) if settled else 0
    profit_str = ("+" if profit >= 0 else "") + f"{profit:.2f}"
    profit_color = accent if profit >= 0 else LOSS
    best_win = ("+" + f"{best:.2f}u") if best > 0 else "—"
    period = meta.get("period", "THIS WEEK")
    handle = meta.get("handle", "@puntmatenz")

    # ── Slide 1: The Record ──
    s1 = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    d1 = ScaledDraw(ImageDraw.Draw(s1))

    # Wordmark + period pill
    lkup = _load_lockup(56)
    if lkup:
        s1.paste(lkup, _sp((pad, pad)), lkup)
    else:
        _wordmark(d1, pad, pad + 8, 28, accent)
    pp_f = _f("SpaceMono-Bold.ttf", 22)
    ppb = d1.textbbox((0, 0), period, font=pp_f)
    ppw = ppb[2] + 40
    _rrect(d1, [W - pad - ppw, pad + 4, W - pad, pad + 48], r=14, outline=accent, width=2)
    d1.text((W - pad - ppw + 20, pad + 14), period, font=pp_f, fill=accent)

    # Kicker
    kf = _f("SpaceMono-Bold.ttf", 26)
    d1.text((pad, pad + 108), "// THE RESULTS", font=kf, fill=accent)

    # Big W-L score
    score_f = _f("Archivo-Black.ttf", 220)
    score_text = f"{wins}"
    d1.text((pad, pad + 160), score_text, font=score_f, fill="#EAF7EF")
    sw = d1.textbbox((pad, pad + 160), score_text, font=score_f)[2]
    dash_f = _f("Archivo-Black.ttf", 220)
    d1.text((sw, pad + 160), "–", font=dash_f, fill=MUTE)
    dw = d1.textbbox((sw, pad + 160), "–", font=dash_f)[2]
    d1.text((dw, pad + 160), str(losses), font=score_f, fill=accent)

    sub_f = _f("SpaceGrotesk-Medium.ttf", 38)
    d1.text((pad, pad + 160 + 230), f"{wins + losses} picks settled · {strike_rate}% strike rate", font=sub_f, fill=NIGHT["muted"])

    # Two stat cards
    sc_y = H - pad - 200
    for i, (lbl, val, col) in enumerate([
        ("PROFIT / LOSS", f"{profit_str}u", profit_color),
        ("BEST WIN",       best_win,        accent),
    ]):
        sx = pad + i * ((W - 2 * pad) // 2 + 14)
        sw2 = (W - 2 * pad) // 2 - 7
        _rrect(d1, [sx, sc_y, sx + sw2, sc_y + 106], r=22, fill=NIGHT["surface"], outline=accent_dim, width=2)
        d1.text((sx + 28, sc_y + 18), lbl, font=_f("SpaceMono-Regular.ttf", 20), fill=MUTE)
        d1.text((sx + 28, sc_y + 52), val, font=_f("SpaceMono-Bold.ttf", 52), fill=col)

    d1.line([(pad, H - pad - 56), (W - pad, H - pad - 56)], fill=NIGHT["dimmer"], width=1)
    hf = _f("SpaceGrotesk-Medium.ttf", 24)
    d1.text((pad, H - pad - 40), handle, font=hf, fill="#EAF7EF")
    r18t = "R18 · Gamble responsibly · 0800 654 655"
    r18b = d1.textbbox((0, 0), r18t, font=_f("SpaceMono-Regular.ttf", 22))
    d1.text((W - pad - (r18b[2] - r18b[0]), H - pad - 40), r18t, font=_f("SpaceMono-Regular.ttf", 22), fill=MUTE)
    disc_fr1 = _f("SpaceMono-Regular.ttf", 17)
    disc_txtr1 = "Odds indicative only. Confirm with your betting provider."
    disc_bbr1 = d1.textbbox((0, 0), disc_txtr1, font=disc_fr1)
    d1.text(((W - (disc_bbr1[2] - disc_bbr1[0])) // 2, H - pad - 14), disc_txtr1, font=disc_fr1, fill="#888888")

    # ── Slide 2: The Card ──
    s2 = Image.new("RGB", (W * S, H * S), NIGHT["bg"])
    d2 = ScaledDraw(ImageDraw.Draw(s2))
    d2.text((pad, pad), "// THE CARD", font=_f("SpaceMono-Bold.ttf", 26), fill=accent)
    pd_f = _f("SpaceMono-Regular.ttf", 22)
    pdb = d2.textbbox((0, 0), period, font=pd_f)
    d2.text((W - pad - (pdb[2] - pdb[0]), pad + 7), period, font=pd_f, fill=MUTE)

    row_h = 102
    row_top = pad + 68
    for idx, row in enumerate(rows):
        ry = row_top + idx * (row_h + 14)
        _rrect(d2, [pad, ry, W - pad, ry + row_h], r=20, fill=NIGHT["surface"])
        # Result badge
        _rrect(d2, [pad + 18, ry + 18, pad + 130, ry + 66], r=10, fill=row["tag_bg"])
        badge_f = _f("SpaceMono-Bold.ttf", 22)
        bf_bb = d2.textbbox((0, 0), row["result"], font=badge_f)
        bx = pad + 18 + (112 - (bf_bb[2] - bf_bb[0])) // 2
        d2.text((bx, ry + 28), row["result"], font=badge_f, fill=row["tag_color"])
        # Selection + match
        d2.text((pad + 148, ry + 12), row.get("selection", ""), font=_f("SpaceGrotesk-Bold.ttf", 31), fill=NIGHT["text"])
        d2.text((pad + 148, ry + 52), row.get("match", ""), font=_f("SpaceGrotesk-Medium.ttf", 20), fill=MUTE)
        # Odds right
        o_f = _f("SpaceMono-Bold.ttf", 36)
        ob = d2.textbbox((0, 0), str(row.get("odds", "")), font=o_f)
        d2.text((W - pad - (ob[2] - ob[0]) - 18, ry + 32), str(row.get("odds", "")), font=o_f, fill=row["odds_color"])

    # Summary bar — measure profit first so text column doesn't overlap it
    sumbar_top = row_top + len(rows) * (row_h + 14) + 14
    _rrect(d2, [pad, sumbar_top, W - pad, sumbar_top + 110], r=24, fill=NIGHT["surface"], outline=accent_dim, width=2)
    prof_f = _f("SpaceMono-Bold.ttf", 60)
    profit_label = f"{profit_str}u"
    pfb = d2.textbbox((0, 0), profit_label, font=prof_f)
    prof_w = pfb[2] - pfb[0]
    profit_x = W - pad - prof_w - 30
    d2.text((profit_x, sumbar_top + 22), profit_label, font=prof_f, fill=profit_color)
    # Left column: stats + summary, constrained to not enter profit zone
    text_max_x = profit_x - 20
    d2.text((pad + 30, sumbar_top + 14), f"{wins}W · {losses}L · {strike_rate}% STRIKE",
            font=_f("SpaceMono-Regular.ttf", 20), fill=MUTE)
    summary_f = _f("SpaceGrotesk-Bold.ttf", 26)
    summary_txt = meta.get("summary", "Another green week on the board.")
    # Truncate summary if too wide
    while summary_txt:
        sb = d2.textbbox((0, 0), summary_txt, font=summary_f)
        if pad + 30 + (sb[2] - sb[0]) <= text_max_x:
            break
        summary_txt = summary_txt[:-2].rstrip()
    d2.text((pad + 30, sumbar_top + 56), summary_txt, font=summary_f, fill=NIGHT["text"])

    # CTA
    cta_y2 = H - pad - 90
    d2.ellipse([pad, cta_y2, pad + 48, cta_y2 + 48], fill=accent)
    _draw_value_arrow(d2, pad + 24, cta_y2 + 24, 38, "#0B0F0D")
    d2.text((pad + 64, cta_y2 + 4), f"Follow {handle}", font=_f("SpaceGrotesk-Bold.ttf", 30), fill=NIGHT["text"])
    r18s = "R18 · Gamble responsibly · 0800 654 655"
    r18sb = d2.textbbox((0, 0), r18s, font=_f("SpaceGrotesk-Medium.ttf", 18))
    d2.text((W - pad - (r18sb[2] - r18sb[0]), cta_y2 + 12), r18s, font=_f("SpaceGrotesk-Medium.ttf", 18), fill=MUTE)
    disc_fr2 = _f("SpaceMono-Regular.ttf", 17)
    disc_txtr2 = "Odds indicative only. Confirm with your betting provider."
    disc_bbr2 = d2.textbbox((0, 0), disc_txtr2, font=disc_fr2)
    d2.text(((W - (disc_bbr2[2] - disc_bbr2[0])) // 2, cta_y2 + 38), disc_txtr2, font=disc_fr2, fill="#888888")

    # Save (downscale via LANCZOS for crisp output)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    paths = []
    for slide, label in zip([s1, s2], ["1_record", "2_card"]):
        path = f"{output_dir}/{date_str}_results_{label}.png"
        _save(slide, path)
        paths.append(path)
    return paths


# ── Public API ────────────────────────────────────────────────────────────────

def generate_carousel(pick, output_dir):
    """
    Generate a 3-slide carousel for a single pick.
    Uses Betslip Night or Matchday Print based on pick metadata.
    Returns list of 3 file paths.
    """
    os.makedirs(output_dir, exist_ok=True)

    big_game = pick.get("big_game", False)
    # Matchday Print for big events; Betslip Night for everything else
    look = "print" if big_game else "night"

    date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    safe_match = pick.get("match", "pick").replace(" vs ", "_vs_").replace(" ", "")[:30]
    prefix = f"{output_dir}/{date_str}_{safe_match}_{look}"

    if look == "print":
        slides = [
            _print_slide1_cover(pick),
            _print_slide2_tip(pick),
            _print_slide3_breakdown(pick),
        ]
    else:
        slides = [
            _night_slide1_cover(pick),
            _night_slide2_tip(pick),
            _night_slide3_breakdown(pick),
        ]

    paths = []
    labels = ["1_cover", "2_tip", "3_breakdown"]
    for img, label in zip(slides, labels):
        path = f"{prefix}_{label}.png"
        _save(img, path)
        paths.append(path)

    return paths


def generate_picks_image(picks, output_dir=None):
    """
    Generate carousels for all picks.
    Backward-compatible entry point for main.py.
    Returns the path of the first slide of the first pick (for legacy IG posting).
    """
    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')

    all_paths = []
    for pick in picks:
        paths = generate_carousel(pick, output_dir)
        all_paths.extend(paths)

    # Return cover slide of first pick for backward compatibility
    return all_paths[0] if all_paths else None
