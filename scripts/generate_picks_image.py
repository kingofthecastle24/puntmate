"""
generate_picks_image.py — Professional Instagram picks card generator.
Creates ONE 1080×1080px daily card with 3 personality rows (Investor/Punter/Gambler).
Each personality selects the best pick from all today's matches.

Design: Auric Edge — dark navy, gold accents, bold modern typography.
Fonts auto-downloaded on first run.
"""

import os
import urllib.request
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# ─── Brand colours ─────────────────────────────────────────────────────────────
NAVY_DEEP  = (5,   10,  25)
NAVY_MID   = (11,  20,  44)
NAVY_CARD  = (18,  30,  62)
NAVY_PANEL = (25,  42,  82)
GOLD       = (201, 168,  75)
GOLD_LIGHT = (225, 198, 118)
WHITE      = (255, 255, 255)
GREY       = (145, 158, 185)
GREY_DIM   = (85,  100, 130)

SIZE   = 1080
MARGIN = 52

# ─── Personality config ─────────────────────────────────────────────────────────
PERSONA = {
    "investor": {
        "label":   "INVESTOR",
        "emoji":   "📊",
        "color":   (90, 175, 255),    # cool blue
        "tagline": "Safe. Steady. Long game.",
    },
    "punter": {
        "label":   "PUNTER",
        "emoji":   "🎯",
        "color":   GOLD,
        "tagline": "Form. Value. Gut feel.",
    },
    "gambler": {
        "label":   "GAMBLER",
        "emoji":   "🎰",
        "color":   (250, 90, 110),    # hot red
        "tagline": "Long shots. Big returns.",
    },
}

# ─── Sport labels ────────────────────────────────────────────────────────────────
SPORT_LABELS = {
    "soccer_fifa_world_cup":     "WORLD CUP",
    "rugbyleague_nrl":           "NRL",
    "basketball_nba":            "NBA",
    "rugbyunion_super_rugby":    "SUPER RUGBY",
    "tennis_atp_french_open":    "ATP",
    "tennis_wta_french_open":    "WTA",
}

SPORT_COLORS = {
    "soccer_fifa_world_cup":     (20, 155, 85),
    "rugbyleague_nrl":           (210, 45,  45),
    "basketball_nba":            (195, 75,  25),
    "rugbyunion_super_rugby":    (210, 45,  45),
    "tennis_atp_french_open":    (175, 65, 135),
    "tennis_wta_french_open":    (175, 65, 135),
}

# ─── Font management ────────────────────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(__file__), '..', '.fonts')
FONTS = {
    "bebas":      ("https://github.com/googlefonts/bebasneue/raw/main/fonts/ttf/BebasNeue-Regular.ttf", "BebasNeue-Regular.ttf"),
    "inter_bold": ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Bold.ttf", "Inter-Bold.ttf"),
    "inter_semi": ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-SemiBold.ttf", "Inter-SemiBold.ttf"),
    "inter":      ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.ttf", "Inter-Regular.ttf"),
}

def _ensure_fonts():
    os.makedirs(FONT_DIR, exist_ok=True)
    for key, (url, filename) in FONTS.items():
        path = os.path.join(FONT_DIR, filename)
        if not os.path.exists(path):
            try:
                print(f"  Downloading font: {filename}...")
                urllib.request.urlretrieve(url, path)
            except Exception as e:
                print(f"  ⚠️  Font download failed ({filename}): {e}")

def _font(key, size):
    _, filename = FONTS[key]
    path = os.path.join(FONT_DIR, filename)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    for fallback in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]:
        if os.path.exists(fallback):
            try:
                return ImageFont.truetype(fallback, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ─── Drawing helpers ─────────────────────────────────────────────────────────────

def _gradient_bg(img):
    """Dark navy vertical gradient background."""
    draw = ImageDraw.Draw(img)
    h = SIZE
    for y in range(h):
        t = y / (h - 1)
        r = int(NAVY_MID[0] + (NAVY_DEEP[0] - NAVY_MID[0]) * t)
        g = int(NAVY_MID[1] + (NAVY_DEEP[1] - NAVY_MID[1]) * t)
        b = int(NAVY_MID[2] + (NAVY_DEEP[2] - NAVY_MID[2]) * t)
        draw.line([(0, y), (SIZE, y)], fill=(r, g, b))

def _tw(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]

def _th(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]

def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _tw(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def _rr(draw, x0, y0, x1, y1, r=16, fill=None, outline=None, ow=2):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=ow)

# ─── Card builder ─────────────────────────────────────────────────────────────────

def _build_card(picks, date_str):
    """
    Build one 1080×1080 daily picks card.
    picks: list of 3 dicts (one per personality, each from its best match)
    """
    img = Image.new("RGB", (SIZE, SIZE), NAVY_DEEP)
    _gradient_bg(img)
    draw = ImageDraw.Draw(img)

    # ── Top gold rule ──────────────────────────────────────────────────────────
    draw.rectangle([0, 0, SIZE, 6], fill=GOLD)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_brand   = _font("bebas", 60)
    f_brandnz = _font("bebas", 40)
    f_date    = _font("inter_semi", 14)
    f_tagline = _font("inter", 13)
    f_persona = _font("inter_bold", 20)
    f_match   = _font("inter_semi", 15)
    f_sport   = _font("inter", 12)
    f_pick    = _font("bebas", 42)
    f_odds    = _font("bebas", 72)
    f_market  = _font("inter", 12)
    f_reason  = _font("inter", 13)
    f_footer  = _font("inter", 12)

    # ── Brand header ──────────────────────────────────────────────────────────
    y = 16
    draw.text((MARGIN, y), "PUNTMATE", font=f_brand, fill=WHITE)
    bw = _tw(draw, "PUNTMATE", f_brand)
    draw.text((MARGIN + bw + 6, y + 12), "NZ", font=f_brandnz, fill=GOLD)

    # Date right-aligned
    dw = _tw(draw, date_str.upper(), f_date)
    draw.text((SIZE - MARGIN - dw, y + 22), date_str.upper(), font=f_date, fill=GREY)

    y += _th(draw, "PUNTMATE", f_brand) + 8

    # Tagline
    tagline = "THREE PERSONALITIES · THREE ANGLES · ONE BEST PICK EACH"
    tw_ = _tw(draw, tagline, f_tagline)
    draw.text(((SIZE - tw_) // 2, y), tagline, font=f_tagline, fill=GREY_DIM)
    y += _th(draw, tagline, f_tagline) + 14

    # ── Gold divider ──────────────────────────────────────────────────────────
    draw.rectangle([MARGIN, y, SIZE - MARGIN, y + 2], fill=GOLD)
    y += 16

    # ── Personality rows ──────────────────────────────────────────────────────
    footer_y = SIZE - 60
    usable_h = footer_y - y - 8
    row_gap  = 10
    row_h    = (usable_h - row_gap * 2) // 3

    grouped = {p.get("personality", "punter"): p for p in picks}

    for row_idx, pk in enumerate(["investor", "punter", "gambler"]):
        cfg = PERSONA[pk]
        pick_data = grouped.get(pk, {})

        ry = y + row_idx * (row_h + row_gap)
        rx0, rx1 = MARGIN, SIZE - MARGIN

        # Row panel background
        _rr(draw, rx0, ry, rx1, ry + row_h, r=18, fill=NAVY_CARD)

        # Persona colour left edge bar
        draw.rectangle([rx0, ry + 18, rx0 + 5, ry + row_h - 18], fill=cfg["color"])

        # ── Left section: persona identity ─────────────────────────────────────
        col_persona_w = 190
        lx = rx0 + 22
        ly = ry + 22

        # Persona label
        draw.text((lx, ly), cfg["label"], font=f_persona, fill=cfg["color"])
        ly += _th(draw, cfg["label"], f_persona) + 4

        # Tagline
        for tl in _wrap(draw, cfg["tagline"], f_tagline, col_persona_w - 10):
            draw.text((lx, ly), tl, font=f_tagline, fill=GREY)
            ly += _th(draw, tl, f_tagline) + 2

        ly += 8

        # Sport badge
        if pick_data:
            sport_key = pick_data.get("sport_key", "")
            sport_label_text = SPORT_LABELS.get(sport_key, pick_data.get("sport", "SPORT"))
            sport_color = SPORT_COLORS.get(sport_key, GOLD)
            sw = _tw(draw, sport_label_text, f_sport) + 16
            sh = 22
            _rr(draw, lx, ly, lx + sw, ly + sh, r=11, fill=sport_color)
            draw.text((lx + 8, ly + 4), sport_label_text, font=f_sport, fill=WHITE)
            ly += sh + 6

            # Match name (small)
            match_text = pick_data.get("match", "")
            for ml in _wrap(draw, match_text, f_match, col_persona_w - 10)[:2]:
                draw.text((lx, ly), ml, font=f_match, fill=GREY)
                ly += _th(draw, ml, f_match) + 2

        # Vertical separator
        sep_x = rx0 + col_persona_w + 30
        draw.rectangle([sep_x, ry + 20, sep_x + 1, ry + row_h - 20], fill=(35, 52, 95))

        # ── Centre section: pick + odds ────────────────────────────────────────
        centre_x = sep_x + 20
        centre_w = 230

        if pick_data:
            cy = ry + 20

            # Pick text
            pick_text = pick_data.get("pick", "—").upper()
            for pl in _wrap(draw, pick_text, f_pick, centre_w)[:2]:
                pw = _tw(draw, pl, f_pick)
                draw.text((centre_x + (centre_w - pw) // 2, cy), pl, font=f_pick, fill=WHITE)
                cy += _th(draw, pl, f_pick) + 2

            cy += 4

            # Odds
            odds_str = f"@ {pick_data.get('odds', '—')}"
            ow_ = _tw(draw, odds_str, f_odds)
            draw.text((centre_x + (centre_w - ow_) // 2, cy), odds_str, font=f_odds, fill=GOLD)
            cy += _th(draw, odds_str, f_odds) + 2

            # Market
            market = pick_data.get("market", "")
            if market:
                mw = _tw(draw, market.upper(), f_market)
                draw.text((centre_x + (centre_w - mw) // 2, cy), market.upper(), font=f_market, fill=GREY)

        # Vertical separator 2
        sep2_x = centre_x + centre_w + 20
        draw.rectangle([sep2_x, ry + 20, sep2_x + 1, ry + row_h - 20], fill=(35, 52, 95))

        # ── Right section: reasoning ───────────────────────────────────────────
        reason_x = sep2_x + 20
        reason_w = (SIZE - MARGIN) - reason_x - 16

        if pick_data:
            reasoning = pick_data.get("reasoning", "")
            rlines = _wrap(draw, reasoning, f_reason, reason_w)
            ry2 = ry + 24
            line_h = _th(draw, "X", f_reason) + 4
            max_lines = (row_h - 30) // line_h
            for rline in rlines[:max_lines]:
                draw.text((reason_x, ry2), rline, font=f_reason, fill=GREY)
                ry2 += line_h

    # ── Footer ──────────────────────────────────────────────────────────────────
    fy = footer_y + 6
    draw.rectangle([0, fy - 4, SIZE, fy - 3], fill=GOLD)

    handle = "@puntmatenz"
    draw.text((MARGIN, fy + 4), handle, font=f_footer, fill=GOLD)

    responsible = "Bet responsibly · Problem Gambling Foundation NZ: 0800 664 262"
    rw = _tw(draw, responsible, f_footer)
    draw.text(((SIZE - rw) // 2, fy + 4), responsible, font=f_footer, fill=GREY_DIM)

    # Decorative top-right triangle (brand accent)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(SIZE - 280, 0), (SIZE, 0), (SIZE, 260)], fill=(*GOLD, 12))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    # Bottom gold rule
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, SIZE - 6, SIZE, SIZE], fill=GOLD)

    return img


# ─── Public API ──────────────────────────────────────────────────────────────────

def generate_picks_images(picks, output_dir=None, date_str=None):
    """
    Generate ONE daily picks card (3 personality rows, one pick each).
    Returns list with a single file path.
    """
    _ensure_fonts()

    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")

    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')

    os.makedirs(output_dir, exist_ok=True)

    img = _build_card(picks, date_str)
    fname = f"picks_{datetime.now().strftime('%Y-%m-%d')}.png"
    path = os.path.join(output_dir, fname)
    img.save(path, "PNG", optimize=True)
    print(f"  ✅ Saved daily card: {fname}")
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
        {
            "personality": "investor",
            "sport_key": "soccer_fifa_world_cup",
            "sport": "FIFA World Cup 2026",
            "match": "England vs DR Congo",
            "pick": "England -1.5",
            "market": "Handicap",
            "odds": "1.95",
            "reasoning": "England are a top-10 FIFA ranked side facing a DR Congo outfit with limited World Cup pedigree. Group-stage pressure favours the favourite covering a two-goal margin comfortably.",
            "confidence": "High",
        },
        {
            "personality": "punter",
            "sport_key": "rugbyleague_nrl",
            "sport": "NRL",
            "match": "Melbourne Storm vs Parramatta Eels",
            "pick": "Melbourne Storm",
            "market": "Head to Head",
            "odds": "2.10",
            "reasoning": "Storm at home is always a banker. Parramatta have been inconsistent and Melbourne's defence is the best in the comp right now. Good value at $2.10.",
            "confidence": "High",
        },
        {
            "personality": "gambler",
            "sport_key": "soccer_fifa_world_cup",
            "sport": "FIFA World Cup 2026",
            "match": "Belgium vs Senegal",
            "pick": "Senegal",
            "market": "Head to Head",
            "odds": "4.30",
            "reasoning": "Belgium's golden generation is rusty and Senegal showed serious hunger in qualifying. Africa's champion at a World Cup with chips on their shoulder? That's value at 4.30 all day.",
            "confidence": "Low",
        },
    ]
    paths = generate_picks_images(test_picks, output_dir="/tmp/puntmate_cards_test")
    print("Generated:", paths)
