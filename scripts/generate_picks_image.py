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
import math
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'fonts')
ASSETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'assets')

W, H = 1080, 1350  # 4:5 portrait (brand spec)


# ── Font loader ───────────────────────────────────────────────────────────────

def _f(name, size):
    """Load a font by filename; gracefully falls back to system fonts or default."""
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Fallback chain: DejaVu Sans → Pillow default
    fallbacks = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for fb in fallbacks:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                pass
    return ImageFont.load_default()


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


# ── Cover theme text map ──────────────────────────────────────────────────────

COVER_HEADLINES = {
    "Tip of the Week":    ("TIP OF",   "THE",    "WEEK."),
    "Value Alert":        ("VALUE",    "ALERT.", ""),
    "Daily Pick":         ("DAILY",    "PICK.",  ""),
    "Banker of the Day":  ("BANKER",   "OF",     "THE DAY."),
    "Multi Monday":       ("MULTI",    "MONDAY.",""),
}


# ── Utility drawing helpers ───────────────────────────────────────────────────

def _rrect(draw, box, r, fill=None, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _text_center(draw, text, y, font, fill, width=W):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((width - tw) // 2, y), text, font=font, fill=fill)


def _draw_grid(draw, color=(255, 255, 255, 7), cell=60):
    """Draw the subtle 60×60 grid used on Cover and Breakdown slides."""
    for x in range(0, W, cell):
        draw.line([(x, 0), (x, H)], fill=color, width=1)
    for y in range(0, H, cell):
        draw.line([(0, y), (W, y)], fill=color, width=1)


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

    img = Image.new("RGB", (W, H), NIGHT["bg"])
    draw = ImageDraw.Draw(img)
    _draw_grid(draw)

    pad = 88

    # Top bar — icon + wordmark + sport tag
    icon_cx, icon_cy = pad + 32, pad + 32
    draw.ellipse(
        [icon_cx - 32, icon_cy - 32, icon_cx + 32, icon_cy + 32],
        fill=NIGHT["surface"], outline=accent_dim, width=2
    )
    _draw_value_arrow(draw, icon_cx, icon_cy, 40, accent)

    _wordmark(draw, icon_cx + 50, icon_cy - 14, 28, accent)

    # Sport tag pill
    sport = pick.get("sport_label", "SPORT")
    tag_f = _f("SpaceMono-Bold.ttf", 24)
    tag_bbox = draw.textbbox((0, 0), sport, font=tag_f)
    tag_w = tag_bbox[2] + 40
    tag_x = W - pad - tag_w
    _rrect(draw, [tag_x, icon_cy - 22, tag_x + tag_w, icon_cy + 22], r=999, outline=accent, width=2)
    draw.text((tag_x + 20, icon_cy - 16), sport, font=tag_f, fill=accent)

    # Cover kicker
    theme = pick.get("coverTheme", "Daily Pick")
    kicker_f = _f("SpaceMono-Bold.ttf", 26)
    kicker_y = pad + 120
    draw.text((pad, kicker_y), f"// {theme.upper()}", font=kicker_f, fill=accent)

    # Giant headline
    lines = COVER_HEADLINES.get(theme, ("BEST", "VALUE", "BET."))
    headline_f = _f("Archivo-Black.ttf", 172)
    line_h = 155
    hy = kicker_y + 70
    for i, line in enumerate(lines):
        if not line:
            continue
        col = accent if i == 1 else "#EAF7EF"
        draw.text((pad, hy), line, font=headline_f, fill=col)
        hy += line_h

    # Subline
    sub_f = _f("SpaceGrotesk-Medium.ttf", 34)
    sub_y = H - pad - 160
    draw.text((pad, sub_y), "One selection. One slide. Locked in below.", font=sub_f, fill=NIGHT["muted"])

    # SWIPE →
    swipe_f = _f("SpaceMono-Bold.ttf", 26)
    swipe_y = sub_y + 60
    draw.text((pad, swipe_y), "SWIPE  →", font=swipe_f, fill=accent)

    # Bottom rule
    draw.line([(pad, H - pad - 50), (W - pad, H - pad - 50)], fill=NIGHT["dimmer"], width=1)

    # Handle
    handle_f = _f("SpaceGrotesk-Medium.ttf", 24)
    draw.text((pad, H - pad - 38), "@puntmatenz", font=handle_f, fill="#EAF7EF")

    return img


def _night_slide2_tip(pick):
    """Betslip Night — The Tip slide: betslip card."""
    palette = NIGHT_ACCENTS.get(pick.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent = palette["accent"]
    accent_dim = palette["accent_dim"]

    img = Image.new("RGB", (W, H), NIGHT["bg"])
    draw = ImageDraw.Draw(img)

    pad = 80

    # Header
    header_f = _f("SpaceMono-Bold.ttf", 26)
    draw.text((pad, pad), "// THE PICK", font=header_f, fill=accent)

    market_f = _f("SpaceMono-Regular.ttf", 24)
    draw.text((pad, pad + 50), pick.get("market", "Head to Head").upper(), font=market_f, fill=NIGHT["muted"])

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
    draw.text((W - pad - 80, card_top + 42), "1 LEG", font=leg_f, fill=NIGHT["muted"])

    # Match
    lbl_f = _f("SpaceMono-Regular.ttf", 20)
    val_f  = _f("SpaceGrotesk-Bold.ttf", 46)
    sel_f  = _f("SpaceGrotesk-Bold.ttf", 80)
    mkt_f  = _f("SpaceMono-Bold.ttf", 24)

    cy = card_top + 120
    draw.text((pad + 44, cy), "MATCH", font=lbl_f, fill=NIGHT["muted"])
    cy += 32
    draw.text((pad + 44, cy), pick.get("match", ""), font=val_f, fill=NIGHT["text"])

    cy += 70
    draw.text((pad + 44, cy), "SELECTION", font=lbl_f, fill=NIGHT["muted"])
    cy += 30
    selection = pick.get("selection", "")
    draw.text((pad + 44, cy), selection, font=sel_f, fill=NIGHT["text"])

    # Market pill
    cy += 100
    pill_text = pick.get("market", "Head to Head")
    pill_bbox = draw.textbbox((0, 0), pill_text, font=mkt_f)
    pill_w = pill_bbox[2] + 52
    _rrect(draw, [pad + 44, cy, pad + 44 + pill_w, cy + 52], r=999,
           outline=accent_dim, width=2)
    draw.text((pad + 70, cy + 12), pill_text, font=mkt_f, fill=accent)

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

    # Odds section
    odds_lbl_y = div_y + 28
    draw.text((pad + 44, odds_lbl_y), "DECIMAL ODDS", font=lbl_f, fill=NIGHT["muted"])
    draw.text((pad + 44, odds_lbl_y + 28), pick.get("insight", ""), font=_f("SpaceGrotesk-Medium.ttf", 24), fill=NIGHT["muted"])

    odds_f = _f("SpaceMono-Bold.ttf", 118)
    odds_str = str(pick.get("odds", "2.00"))
    odds_bbox = draw.textbbox((0, 0), odds_str, font=odds_f)
    odds_x = W - pad - (odds_bbox[2] - odds_bbox[0]) - 20
    draw.text((odds_x, div_y + 20), odds_str, font=odds_f, fill=accent)

    # Compliance
    comp_f = _f("SpaceGrotesk-Medium.ttf", 20)
    draw.text((pad, H - pad + 10), "R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz",
              font=comp_f, fill=NIGHT["muted"])

    return img


def _night_slide3_breakdown(pick):
    """Betslip Night — The Breakdown slide: analysis + confidence + CTA."""
    palette = NIGHT_ACCENTS.get(pick.get("palette", "green"), NIGHT_ACCENTS["green"])
    accent = palette["accent"]
    accent_dim = palette["accent_dim"]

    img = Image.new("RGB", (W, H), NIGHT["bg"])
    draw = ImageDraw.Draw(img)
    _draw_grid(draw)

    pad = 80

    # Header
    header_f = _f("SpaceMono-Bold.ttf", 26)
    draw.text((pad, pad), "// THE BREAKDOWN", font=header_f, fill=accent)

    conf_lbl_f = _f("SpaceMono-Regular.ttf", 22)
    draw.text((pad, pad + 50), f"{pick.get('confidenceLabel', 'MODERATE')} CONFIDENCE", font=conf_lbl_f, fill=NIGHT["muted"])

    # Risk chips
    chip_f = _f("SpaceMono-Regular.ttf", 20)
    chips = [pick.get("riskTagline", "SOLID VALUE"), pick.get("tier", "punter").upper(), pick.get("sport_label", "")]
    cx = pad
    cy = pad + 100
    for chip in chips:
        if not chip:
            continue
        cb = draw.textbbox((0, 0), chip, font=chip_f)
        cw = cb[2] + 40
        _rrect(draw, [cx, cy, cx + cw, cy + 44], r=999, outline=accent_dim, width=2)
        draw.text((cx + 20, cy + 10), chip, font=chip_f, fill=accent)
        cx += cw + 16

    # Main analysis card
    card_top = cy + 70
    card_bot = H - pad - 230
    _rrect(draw, [pad, card_top, W - pad, card_bot], r=28,
           fill=NIGHT["surface"], outline=accent_dim, width=2)

    inner_pad = pad + 44

    # Competition / sport label
    comp_f = _f("SpaceMono-Regular.ttf", 22)
    draw.text((inner_pad, card_top + 36), pick.get("sport_label", ""), font=comp_f, fill=NIGHT["muted"])

    # Match name
    match_f = _f("SpaceGrotesk-Bold.ttf", 38)
    draw.text((inner_pad, card_top + 76), pick.get("match", ""), font=match_f, fill=NIGHT["text"])

    # Sport tag pill
    tag_f = _f("SpaceMono-Bold.ttf", 20)
    tag = pick.get("sport_label", "")
    tag_bbox = draw.textbbox((0, 0), tag, font=tag_f)
    tag_w = tag_bbox[2] + 36
    tag_y = card_top + 76
    _rrect(draw, [W - pad - tag_w - 20, tag_y + 4, W - pad - 20, tag_y + 44], r=999,
           outline=accent, width=2)
    draw.text((W - pad - tag_w + 2, tag_y + 12), tag, font=tag_f, fill=accent)

    # Divider
    div_y = card_top + 150
    draw.line([(inner_pad, div_y), (W - inner_pad, div_y)], fill=NIGHT["dimmer"], width=1)

    # Selection + odds inline
    sel_f = _f("SpaceGrotesk-Bold.ttf", 52)
    odds_f = _f("SpaceMono-Bold.ttf", 44)
    sel_y = div_y + 24
    draw.text((inner_pad, sel_y), pick.get("selection", ""), font=sel_f, fill=NIGHT["text"])
    odds_str = f"@ {pick.get('odds', '')}"
    draw.text((inner_pad, sel_y + 72), odds_str, font=odds_f, fill=accent)

    # Confidence dots
    dots_y = sel_y + 140
    draw.text((inner_pad, dots_y), "CONFIDENCE", font=comp_f, fill=NIGHT["muted"])
    _draw_confidence_dots(draw, inner_pad + 200, dots_y, pick.get("confidence", 3), accent=accent)

    # The Read
    read_lbl_y = dots_y + 50
    read_f_lbl = _f("SpaceMono-Regular.ttf", 22)
    draw.text((inner_pad, read_lbl_y), "THE READ", font=read_f_lbl, fill=NIGHT["muted"])

    analysis_f = _f("SpaceGrotesk-Medium.ttf", 32)
    analysis = pick.get("analysis", "")
    # Word wrap
    words = analysis.split()
    lines, line = [], []
    for w in words:
        test = ' '.join(line + [w])
        bb = draw.textbbox((0, 0), test, font=analysis_f)
        if bb[2] > (W - inner_pad - pad - 40) and line:
            lines.append(' '.join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(' '.join(line))

    analysis_y = read_lbl_y + 38
    for l in lines[:4]:  # max 4 lines
        draw.text((inner_pad, analysis_y), l, font=analysis_f, fill="#C7D6CE")
        analysis_y += 44

    # Bottom divider
    draw.line([(pad, card_bot + 20), (W - pad, card_bot + 20)], fill=NIGHT["dimmer"], width=1)

    # Follow CTA
    cta_y = card_bot + 40
    cta_circle_x = pad + 28
    draw.ellipse([pad, cta_y, pad + 56, cta_y + 56], fill=accent)
    _draw_value_arrow(draw, cta_circle_x, cta_y + 28, 34, NIGHT["bg"])

    cta_f = _f("SpaceGrotesk-Bold.ttf", 38)
    draw.text((pad + 76, cta_y + 8), "Follow @puntmatenz", font=cta_f, fill=NIGHT["text"])

    edge_f = _f("SpaceMono-Bold.ttf", 26)
    draw.text((pad, cta_y + 70), "DAILY EDGE  →", font=edge_f, fill=accent)

    comp_f2 = _f("SpaceGrotesk-Medium.ttf", 20)
    draw.text((pad, H - pad + 10), "R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz",
              font=comp_f2, fill=NIGHT["muted"])

    return img


# ── Slide generators — Matchday Print ────────────────────────────────────────

def _print_slide1_cover(pick):
    """Matchday Print — Cover slide. Anton for big headlines, Barlow Condensed for kickers."""
    img = Image.new("RGB", (W, H), PRINT["bg"])
    draw = ImageDraw.Draw(img)

    pad = 72

    # Red top bar
    draw.rectangle([0, 0, W, 100], fill=PRINT["red"])
    wm_f = _f("Archivo-Black.ttf", 36)
    draw.text((pad, 30), "PUNTMATE", font=wm_f, fill=PRINT["yellow"])
    sport_f = _f("BarlowCondensed-Bold.ttf", 30)
    sport = pick.get("sport_label", "SPORT")
    draw.text((W - pad - 180, 33), sport, font=sport_f, fill=PRINT["bg"])

    # Kicker — Barlow Condensed
    kicker_f = _f("BarlowCondensed-SemiBold.ttf", 30)
    theme = pick.get("coverTheme", "Daily Pick")
    draw.text((pad, 130), f"// {theme.upper()}", font=kicker_f, fill=PRINT["red"])

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

    return img


def _print_slide2_tip(pick):
    """Matchday Print — The Tip slide."""
    img = Image.new("RGB", (W, H), PRINT["bg"])
    draw = ImageDraw.Draw(img)

    pad = 72

    # Red top bar
    draw.rectangle([0, 0, W, 100], fill=PRINT["red"])
    wm_f = _f("Archivo-Black.ttf", 36)
    draw.text((pad, 30), "PUNTMATE", font=wm_f, fill=PRINT["yellow"])

    # THE PICK kicker — Barlow Condensed
    kicker_f = _f("BarlowCondensed-Bold.ttf", 32)
    draw.text((pad, 120), "// THE PICK", font=kicker_f, fill=PRINT["red"])

    # MATCH — Barlow Condensed
    lbl_f = _f("BarlowCondensed-SemiBold.ttf", 26)
    draw.text((pad, 185), "MATCH", font=lbl_f, fill=PRINT["muted"])
    match_f = _f("BarlowCondensed-Bold.ttf", 56)
    draw.text((pad, 215), pick.get("match", ""), font=match_f, fill=PRINT["ink"])

    # Red rule
    draw.rectangle([pad, 285, W - pad, 292], fill=PRINT["red"])

    # Giant selection — Anton
    sel_f = _f("Anton-Regular.ttf", 128)
    draw.text((pad, 308), pick.get("selection", ""), font=sel_f, fill=PRINT["ink"])

    # Market pill
    mkt_f = _f("BarlowCondensed-Bold.ttf", 28)
    mkt_txt = pick.get("market", "HEAD TO HEAD").upper()
    mkt_bb = draw.textbbox((0, 0), mkt_txt, font=mkt_f)
    mkt_w = mkt_bb[2] + 48
    _rrect(draw, [pad, 468, pad + mkt_w, 516], r=999, fill=PRINT["red"])
    draw.text((pad + 24, 478), mkt_txt, font=mkt_f, fill=PRINT["bg"])

    # Odds — Anton for the number
    odds_lbl_f = _f("BarlowCondensed-SemiBold.ttf", 26)
    draw.text((pad, 560), "DECIMAL ODDS", font=odds_lbl_f, fill=PRINT["muted"])
    odds_f = _f("Anton-Regular.ttf", 150)
    draw.text((pad, 592), str(pick.get("odds", "")), font=odds_f, fill=PRINT["red"])

    # Insight line
    insight_f = _f("BarlowCondensed-SemiBold.ttf", 32)
    draw.text((pad, 768), pick.get("insight", ""), font=insight_f, fill=PRINT["muted"])

    # Yellow bottom strip
    strip_y = H - 140
    draw.rectangle([0, strip_y, W, strip_y + 100], fill=PRINT["yellow"])
    swipe_f = _f("BarlowCondensed-Bold.ttf", 34)
    draw.text((pad, strip_y + 32), "SWIPE  →  SEE THE BREAKDOWN", font=swipe_f, fill=PRINT["ink"])

    comp_f = _f("BarlowCondensed-SemiBold.ttf", 22)
    draw.text((pad, H - 38), "R18 · GAMBLE RESPONSIBLY · 0800 654 655", font=comp_f, fill=PRINT["muted"])

    return img


def _print_slide3_breakdown(pick):
    """Matchday Print — The Breakdown slide."""
    img = Image.new("RGB", (W, H), PRINT["bg"])
    draw = ImageDraw.Draw(img)

    pad = 72

    # Red top bar
    draw.rectangle([0, 0, W, 100], fill=PRINT["red"])
    wm_f = _f("Archivo-Black.ttf", 36)
    draw.text((pad, 30), "PUNTMATE", font=wm_f, fill=PRINT["yellow"])

    kicker_f = _f("BarlowCondensed-Bold.ttf", 32)
    draw.text((pad, 120), "// THE BREAKDOWN", font=kicker_f, fill=PRINT["red"])

    # Confidence + risk — Barlow
    conf_f = _f("BarlowCondensed-SemiBold.ttf", 28)
    draw.text((pad, 185), f"CONFIDENCE: {pick.get('confidenceLabel', 'MODERATE')}", font=conf_f, fill=PRINT["muted"])
    draw.text((pad, 225), f"RISK: {pick.get('riskTagline', 'GOOD VALUE')}", font=conf_f, fill=PRINT["ink"])

    # Red rule
    draw.rectangle([pad, 280, W - pad, 287], fill=PRINT["red"])

    # Selection — Anton
    sel_f = _f("Anton-Regular.ttf", 80)
    draw.text((pad, 305), pick.get("selection", ""), font=sel_f, fill=PRINT["ink"])
    odds_f = _f("BarlowCondensed-Bold.ttf", 56)
    draw.text((pad, 400), f"@ {pick.get('odds', '')}", font=odds_f, fill=PRINT["red"])

    # Confidence dots
    draw.text((pad, 478), "CONFIDENCE", font=conf_f, fill=PRINT["muted"])
    for i in range(5):
        fill = PRINT["ink"] if i < pick.get("confidence", 3) else PRINT["muted"]
        draw.ellipse([pad + 170 + i * 34, 480, pad + 170 + i * 34 + 22, 502], fill=fill)

    # Analysis
    draw.text((pad, 540), "THE READ", font=conf_f, fill=PRINT["muted"])
    analysis_f = _f("BarlowCondensed-SemiBold.ttf", 34)
    analysis = pick.get("analysis", "")
    words = analysis.split()
    lines_out, line = [], []
    for w in words:
        test = ' '.join(line + [w])
        bb = draw.textbbox((0, 0), test, font=analysis_f)
        if bb[2] > W - pad * 2 and line:
            lines_out.append(' '.join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines_out.append(' '.join(line))

    ay = 586
    for l in lines_out[:6]:
        draw.text((pad, ay), l, font=analysis_f, fill=PRINT["ink"])
        ay += 48

    # Yellow CTA strip
    strip_y = H - 140
    draw.rectangle([0, strip_y, W, strip_y + 100], fill=PRINT["yellow"])
    cta_f = _f("BarlowCondensed-Bold.ttf", 34)
    draw.text((pad, strip_y + 32), "FOLLOW @PUNTMATENZ · DAILY PICKS", font=cta_f, fill=PRINT["ink"])

    comp_f = _f("BarlowCondensed-SemiBold.ttf", 22)
    draw.text((pad, H - 38), "R18 · GAMBLE RESPONSIBLY · 0800 654 655", font=comp_f, fill=PRINT["muted"])

    return img


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
        img.save(path, "PNG", optimize=True)
        print(f"  Saved: {path}")
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
