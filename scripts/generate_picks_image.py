"""
generate_picks_image.py — PuntMate NZ daily picks card generator.
Creates one 1080x1350 portrait PNG showing the day's three picks (Investor/Punter/Gambler).

Design: "Neon Oracle" — pure black, surgical neon green accents, editorial data-forward layout.
Uses Pillow with bundled fonts from ../fonts/ (BigShoulders, InstrumentSans, GeistMono).
"""

import os
import math
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# ── Font paths ────────────────────────────────────────────────────────────────
FONTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'fonts')
LOGO_PATH = os.path.join(os.path.dirname(__file__), '..', 'assets', 'logo.png')

def _f(name, size):
    try:
        return ImageFont.truetype(os.path.join(FONTS_DIR, name), size)
    except Exception:
        return ImageFont.load_default()

# ── Palette ───────────────────────────────────────────────────────────────────
BLACK    = "#000000"
CARD_BG  = "#0A0A0A"
BORDER   = "#1A1A1A"
WHITE    = "#FFFFFF"
GREEN    = "#00FF87"
ORANGE   = "#FF8C00"
RED      = "#FF3B5C"
GREY_HI  = "#AAAAAA"
GREY_MID = "#666666"
GREY_LO  = "#2E2E2E"
DIVIDER  = "#1A1A1A"

PERSONA_CONFIG = {
    "investor": {"label": "INVESTOR", "sub": "LOWEST RISK",      "color": GREEN},
    "punter":   {"label": "PUNTER",   "sub": "CALCULATED RISK",  "color": ORANGE},
    "gambler":  {"label": "GAMBLER",  "sub": "HIGH REWARD",      "color": RED},
}

SPORT_LABELS = {
    "soccer_fifa_world_cup":  "WORLD CUP",
    "rugbyleague_nrl":        "NRL",
    "basketball_nba":         "NBA",
    "rugbyunion_super_rugby": "SUPER RUGBY",
    "tennis_atp_french_open": "ATP",
    "tennis_wta_french_open": "WTA",
}

CONF_MAP = {"High": 4, "HIGH": 4, "Medium": 3, "MEDIUM": 3, "Low": 2, "LOW": 2}


def _rrect(draw, box, r, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _dots(draw, x, y, filled, total=5, size=7, gap=5, color_on=GREEN):
    for i in range(total):
        cx = x + i * (size + gap)
        c = color_on if i < filled else GREY_LO
        draw.ellipse([cx, y, cx + size, y + size], fill=c)


def _pill(draw, x, y, text, font, fg, bg, pad_x=9, pad_y=3):
    tw = draw.textlength(text, font=font)
    draw.rounded_rectangle([x, y, x + tw + pad_x * 2, y + 18], radius=4, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, fill=fg, font=font)
    return x + tw + pad_x * 2 + 8


def _text_right(draw, x, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text((x - w, y), text, fill=fill, font=font)


def _build_card(picks, date_str):
    W, H   = 1080, 1350
    MARGIN = 40
    CARD_W = W - MARGIN * 2

    # Fonts
    f_brand   = _f("BigShoulders-Bold.ttf",    48)
    f_tier    = _f("BigShoulders-Bold.ttf",    13)
    f_sub     = _f("GeistMono-Regular.ttf",    10)
    f_matchup = _f("InstrumentSans-Bold.ttf",  17)
    f_pick    = _f("InstrumentSans-Bold.ttf",  22)
    f_odds    = _f("InstrumentSans-Bold.ttf",  76)
    f_odds_at = _f("InstrumentSans-Bold.ttf",  13)
    f_bet     = _f("GeistMono-Regular.ttf",    11)
    f_reason  = _f("InstrumentSans-Regular.ttf", 13)
    f_label   = _f("InstrumentSans-Regular.ttf", 11)
    f_date    = _f("GeistMono-Regular.ttf",    11)
    f_league  = _f("GeistMono-Regular.ttf",    10)
    f_footer  = _f("InstrumentSans-Regular.ttf", 11)
    f_foot_b  = _f("InstrumentSans-Bold.ttf",  13)

    img  = Image.new("RGB", (W, H), BLACK)
    draw = ImageDraw.Draw(img)

    # ── Logo ──────────────────────────────────────────────────────────────────
    logo_size = 64
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA").resize((logo_size, logo_size), Image.LANCZOS)
        img.paste(logo, (MARGIN, 32), logo)
    except Exception:
        pass

    lx = MARGIN + logo_size + 14
    draw.text((lx, 38), "PUNT", fill=WHITE, font=f_brand)
    pw = draw.textlength("PUNT", font=f_brand)
    draw.text((lx + pw, 38), "MATE", fill=GREEN, font=f_brand)

    _text_right(draw, W - MARGIN, 38, date_str.upper(), f_date, GREY_MID)
    _text_right(draw, W - MARGIN, 55, "DAILY PICKS", f_date, GREY_LO)

    pill_x = lx
    for label in ["NRL", "WORLD CUP", "NBA"]:
        pill_x = _pill(draw, pill_x, 88, label, f_league, BLACK, GREEN, 8, 3)

    # ── Header divider ────────────────────────────────────────────────────────
    div_y = 118
    draw.line([(MARGIN, div_y), (W - MARGIN, div_y)], fill=GREEN, width=1)
    draw.line([(MARGIN, div_y + 2), (W - MARGIN, div_y + 2)], fill=GREY_LO, width=1)

    # ── Pick cards ────────────────────────────────────────────────────────────
    CARD_H   = 320
    CARD_GAP = 16
    CARD_TOP = div_y + 22
    ACC_W    = 4
    R        = 10

    grouped = {p.get("personality", "punter"): p for p in picks}

    for i, pk in enumerate(["investor", "punter", "gambler"]):
        pick = grouped.get(pk, {})
        cfg  = PERSONA_CONFIG[pk]
        col  = cfg["color"]
        cy   = CARD_TOP + i * (CARD_H + CARD_GAP)
        cx   = MARGIN
        cx1  = MARGIN + CARD_W
        cy1  = cy + CARD_H

        _rrect(draw, [cx, cy, cx1, cy1], R, CARD_BG, outline=BORDER, width=1)
        draw.rectangle([cx, cy + R, cx + ACC_W, cy1 - R], fill=col)

        cont_x = cx + ACC_W + 18

        # Row 1: tier + sublabel + league pill
        r1y = cy + 20
        draw.text((cont_x, r1y), cfg["label"], fill=col, font=f_tier)
        tw = draw.textlength(cfg["label"], font=f_tier)
        draw.text((cont_x + tw + 10, r1y + 1), cfg["sub"], fill=GREY_MID, font=f_sub)

        if pick:
            sport_key   = pick.get("sport_key", "")
            sport_label = SPORT_LABELS.get(sport_key, pick.get("sport", "SPORT").split()[0].upper())
            lp_w = draw.textlength(sport_label, font=f_league)
            lp_x = cx1 - lp_w - 22
            _rrect(draw, [lp_x - 8, r1y - 2, cx1 - 14, r1y + 16], 4, GREY_LO)
            draw.text((lp_x, r1y + 1), sport_label, fill=GREY_HI, font=f_league)

        # Row 2: matchup
        r2y = r1y + 28
        match_str = pick.get("match", "TBD") if pick else "TBD"
        draw.text((cont_x, r2y), match_str.upper(), fill=GREY_HI, font=f_matchup)
        draw.line([(cx + ACC_W + 10, r2y + 26), (cx1 - 14, r2y + 26)], fill=DIVIDER, width=1)

        # Row 3: pick selection + odds
        r3y = r2y + 36
        pick_str = pick.get("pick", "—").upper() if pick else "—"
        draw.text((cont_x, r3y), pick_str, fill=WHITE, font=f_pick)

        odds_str = str(pick.get("odds", "—")) if pick else "—"
        odds_w   = draw.textlength(odds_str, font=f_odds)
        odds_x   = cx1 - 14 - odds_w
        draw.text((odds_x, r3y - 10), odds_str, fill=GREEN, font=f_odds)
        draw.text((odds_x - 18, r3y + 2), "@", fill=GREY_MID, font=f_odds_at)

        market = pick.get("market", "").upper() if pick else ""
        bt_w   = draw.textlength(market, font=f_bet)
        draw.text((cx1 - 14 - bt_w, r3y + 72), market, fill=GREY_MID, font=f_bet)

        # Divider
        div2 = r3y + 90
        draw.line([(cx + ACC_W + 10, div2), (cx1 - 14, div2)], fill=DIVIDER, width=1)

        # Row 4: reasoning
        r4y = div2 + 14
        reason = pick.get("reasoning", "") if pick else ""
        draw.text((cont_x, r4y), reason, fill=GREY_HI, font=f_reason)

        # Row 5: confidence dots
        r5y = r4y + 30
        draw.text((cont_x, r5y + 1), "CONFIDENCE", fill=GREY_MID, font=f_label)
        cl_w = draw.textlength("CONFIDENCE", font=f_label)
        filled = CONF_MAP.get(pick.get("confidence", "Medium"), 3) if pick else 3
        _dots(draw, cont_x + cl_w + 10, r5y + 3, filled, color_on=col)
        draw.text((cont_x, r5y + 18), "STAKE TO WIN", fill=GREY_LO, font=f_label)

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_top = CARD_TOP + 3 * (CARD_H + CARD_GAP) + 12
    draw.line([(MARGIN, footer_top), (W - MARGIN, footer_top)], fill=GREY_LO, width=1)
    fy = footer_top + 14
    draw.text((MARGIN, fy), "@PUNTMATENZ", fill=GREEN, font=f_foot_b)
    hw = draw.textlength("@PUNTMATENZ", font=f_foot_b)
    draw.text((MARGIN + hw + 14, fy + 1), "·  FREE DAILY PICKS  ·  NRL  ·  RUGBY  ·  NBA", fill=GREY_MID, font=f_footer)
    draw.text((MARGIN, fy + 20), "Gamble responsibly. Problem Gambling Foundation NZ: 0800 664 262", fill=GREY_LO, font=f_footer)

    return img


# ── Public API ────────────────────────────────────────────────────────────────

def generate_picks_images(picks, output_dir=None, date_str=None):
    """
    Generate one 1080x1350 portrait daily picks card.
    Returns list with a single file path.
    """
    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')
    os.makedirs(output_dir, exist_ok=True)

    card = _build_card(picks, date_str)
    fname = f"picks_{datetime.now().strftime('%Y-%m-%d')}.png"
    path  = os.path.join(output_dir, fname)
    card.save(path, "PNG", dpi=(300, 300))
    print(f"  ✅ Saved picks card: {fname}")
    return [path]


def generate_picks_image(picks, output_path=None, date_str=None):
    """Single-image alias for backwards compatibility."""
    paths = generate_picks_images(picks, date_str=date_str)
    if output_path and paths:
        import shutil
        shutil.copy(paths[0], output_path)
        return output_path
    return paths[0] if paths else None


if __name__ == "__main__":
    test_picks = [
        {"personality": "investor", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026", "match": "England vs DR Congo",
         "pick": "England -1.5", "market": "Handicap", "odds": "1.95",
         "reasoning": "England are a top-10 FIFA ranked side facing DR Congo with limited World Cup pedigree. Strong value at the handicap.",
         "confidence": "High"},
        {"personality": "punter", "sport_key": "rugbyleague_nrl",
         "sport": "NRL", "match": "Melbourne Storm vs Parramatta Eels",
         "pick": "Melbourne Storm", "market": "Head to Head", "odds": "2.10",
         "reasoning": "Storm at home is always a banker. Parramatta have been inconsistent. Good value at $2.10.",
         "confidence": "High"},
        {"personality": "gambler", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026", "match": "Belgium vs Senegal",
         "pick": "Senegal", "market": "Head to Head", "odds": "4.30",
         "reasoning": "Belgium rusty, Senegal motivated. Africa's champion with chips on their shoulder — value at 4.30 all day.",
         "confidence": "Low"},
    ]
    paths = generate_picks_images(test_picks, output_dir="/tmp/puntmate_test")
    print("Generated:", paths)
