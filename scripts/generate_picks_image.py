"""
generate_picks_image.py — Professional Instagram picks card generator.
Creates one 1080×1080px card per match showing all 3 personality picks.
Auric Edge design: dark navy gradient, gold accents, clean typography.

Fonts auto-downloaded on first run:
  - Bebas Neue Bold  → titles / odds
  - Inter SemiBold   → labels
  - Inter Regular    → body text
"""

import os
import io
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from datetime import datetime

# ─── Brand colours ─────────────────────────────────────────────────────────────
NAVY_DEEP  = (5,   10,  25)
NAVY_MID   = (12,  20,  45)
NAVY_LIGHT = (22,  36,  72)
GOLD       = (201, 168,  75)
GOLD_LIGHT = (230, 200, 120)
WHITE      = (255, 255, 255)
GREY       = (150, 160, 185)
GREY_LIGHT = (200, 210, 230)

SIZE       = 1080
MARGIN     = 52

# ─── Font URLs (Google Fonts CDN) ──────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.dirname(__file__), '..', '.fonts')
FONTS = {
    "bebas":       ("https://github.com/googlefonts/bebasneue/raw/main/fonts/ttf/BebasNeue-Regular.ttf", "BebasNeue-Regular.ttf"),
    "inter_bold":  ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Bold.ttf", "Inter-Bold.ttf"),
    "inter_semi":  ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-SemiBold.ttf", "Inter-SemiBold.ttf"),
    "inter":       ("https://github.com/rsms/inter/raw/master/docs/font-files/Inter-Regular.ttf", "Inter-Regular.ttf"),
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
                print(f"  ⚠️  Could not download {filename}: {e}")

def _font(key, size):
    """Load a font from the font cache, fall back to default."""
    _, filename = FONTS[key]
    path = os.path.join(FONT_DIR, filename)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # System fallback
    for f in ["/System/Library/Fonts/Helvetica.ttc",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(f):
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                pass
    return ImageFont.load_default()

# ─── Sport accent colours ───────────────────────────────────────────────────────
SPORT_COLORS = {
    "soccer_fifa_world_cup":     (20, 140, 80),    # green
    "rugbyleague_nrl":           (220, 50, 50),    # red
    "basketball_nba":            (200, 80, 30),    # orange
    "rugbyunion_super_rugby":    (220, 50, 50),    # red
    "tennis_atp_french_open":    (180, 70, 140),   # clay purple
    "tennis_wta_french_open":    (180, 70, 140),
}

SPORT_LABELS = {
    "soccer_fifa_world_cup":     "FIFA WORLD CUP 2026",
    "rugbyleague_nrl":           "NRL",
    "basketball_nba":            "NBA",
    "rugbyunion_super_rugby":    "SUPER RUGBY",
    "tennis_atp_french_open":    "ATP TENNIS",
    "tennis_wta_french_open":    "WTA TENNIS",
}

PERSONA = {
    "investor": {"label": "INVESTOR", "tag": "[I]", "color": (100, 180, 255)},  # cool blue
    "punter":   {"label": "PUNTER",   "tag": "[P]", "color": GOLD},
    "gambler":  {"label": "GAMBLER",  "tag": "[G]", "color": (255, 100, 120)},  # hot red
}

# ─── Drawing helpers ────────────────────────────────────────────────────────────

def _gradient_rect(img, x0, y0, x1, y1, color_top, color_bot):
    """Draw a vertical gradient rectangle."""
    draw = ImageDraw.Draw(img)
    height = y1 - y0
    for y in range(height):
        t = y / max(height - 1, 1)
        r = int(color_top[0] + (color_bot[0] - color_top[0]) * t)
        g = int(color_top[1] + (color_bot[1] - color_top[1]) * t)
        b = int(color_top[2] + (color_bot[2] - color_top[2]) * t)
        draw.line([(x0, y0 + y), (x1, y0 + y)], fill=(r, g, b))

def _rounded_rect(draw, x0, y0, x1, y1, r=16, fill=None, outline=None, outline_width=2):
    """Draw a rounded rectangle."""
    draw.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline, width=outline_width)

def _text_w(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]

def _text_h(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[3] - bbox[1]

def _center_text(draw, text, y, font, color, x0=0, x1=SIZE):
    w = _text_w(draw, text, font)
    x = x0 + ((x1 - x0) - w) // 2
    draw.text((x, y), text, font=font, fill=color)
    return _text_h(draw, text, font)

def _wrap(draw, text, font, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _text_w(draw, test, font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

# ─── Single match card ──────────────────────────────────────────────────────────

def _make_match_card(match_picks, date_str):
    """
    Create a 1080×1080 card for a single match showing Investor/Punter/Gambler picks.
    match_picks: list of 1-3 dicts with personality, sport_key, match, pick, odds, reasoning
    """
    sport_key = match_picks[0].get("sport_key", "")
    match_name = match_picks[0].get("match", "")
    sport_label = SPORT_LABELS.get(sport_key, match_picks[0].get("sport", "SPORT").upper().replace(" 🌍","").replace(" 🏉","").replace(" 🏀","").replace(" 🎾",""))
    sport_color = SPORT_COLORS.get(sport_key, GOLD)

    img = Image.new("RGB", (SIZE, SIZE), NAVY_DEEP)

    # ── Background gradient ──────────────────────────────────────────────────
    _gradient_rect(img, 0, 0, SIZE, SIZE, NAVY_MID, NAVY_DEEP)

    # Subtle diagonal accent bar (sport color, very translucent)
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.polygon([(SIZE-300, 0), (SIZE, 0), (SIZE, 280)], fill=(*sport_color, 18))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    f_brand    = _font("bebas", 54)
    f_sport    = _font("inter_semi", 16)
    f_match    = _font("bebas", 46)
    f_sublabel = _font("inter_semi", 13)
    f_persona  = _font("inter_bold", 18)
    f_pick     = _font("bebas", 36)
    f_odds     = _font("bebas", 64)
    f_body     = _font("inter", 14)
    f_footer   = _font("inter", 13)

    # ── Top gold rule ─────────────────────────────────────────────────────────
    draw.rectangle([0, 0, SIZE, 5], fill=GOLD)

    # ── Brand header ─────────────────────────────────────────────────────────
    y = 20
    draw.text((MARGIN, y), "PUNTMATE", font=f_brand, fill=WHITE)
    brand_w = _text_w(draw, "PUNTMATE", f_brand)
    draw.text((MARGIN + brand_w + 8, y + 8), "NZ", font=_font("bebas", 38), fill=GOLD)

    # Date top-right
    date_text = date_str.upper()
    dw = _text_w(draw, date_text, f_sport)
    draw.text((SIZE - MARGIN - dw, y + 16), date_text, font=f_sport, fill=GREY)

    y += 64

    # ── Sport pill ────────────────────────────────────────────────────────────
    pill_text = sport_label
    pill_font = f_sport
    pill_w = _text_w(draw, pill_text, pill_font) + 24
    pill_h = 28
    _rounded_rect(draw, MARGIN, y, MARGIN + pill_w, y + pill_h, r=14,
                  fill=(*sport_color, ), outline=None)
    draw.text((MARGIN + 12, y + 5), pill_text, font=pill_font, fill=WHITE)
    y += pill_h + 14

    # ── Match name ────────────────────────────────────────────────────────────
    # Split into home vs away for styling
    parts = match_name.split(" vs ")
    if len(parts) == 2:
        home, away = parts[0].strip(), parts[1].strip()
        match_display = f"{home.upper()}  vs  {away.upper()}"
    else:
        match_display = match_name.upper()

    match_lines = _wrap(draw, match_display, f_match, SIZE - MARGIN * 2)
    for line in match_lines[:2]:
        draw.text((MARGIN, y), line, font=f_match, fill=WHITE)
        y += _text_h(draw, line, f_match) + 4

    y += 8

    # ── Divider ────────────────────────────────────────────────────────────────
    draw.rectangle([MARGIN, y, SIZE - MARGIN, y + 2], fill=GOLD)
    y += 14

    # ── Three personality pick panels ─────────────────────────────────────────
    # Panels fill from current y to 80px above footer
    footer_top  = SIZE - 70
    panel_top   = y
    panel_h     = footer_top - panel_top - 16
    panel_gap   = 12
    avail_w     = SIZE - MARGIN * 2
    panel_w     = (avail_w - panel_gap * 2) // 3

    grouped = {p.get("personality", "punter"): p for p in match_picks}

    for col, pk in enumerate(["investor", "punter", "gambler"]):
        pick_data = grouped.get(pk, {})
        cfg = PERSONA[pk]

        px = MARGIN + col * (panel_w + panel_gap)
        py = panel_top

        # Panel background
        _rounded_rect(draw, px, py, px + panel_w, py + panel_h, r=18, fill=NAVY_LIGHT)

        # Persona colour top accent bar
        draw.rectangle([px + 18, py, px + panel_w - 18, py + 4], fill=cfg["color"])

        inner_y = py + 20

        # Persona label (no emoji — use text tag)
        lbl = cfg["label"]
        lw = _text_w(draw, lbl, f_persona)
        draw.text((px + (panel_w - lw) // 2, inner_y), lbl, font=f_persona, fill=cfg["color"])
        inner_y += _text_h(draw, lbl, f_persona) + 6

        # Small tag
        tag = cfg["tag"]
        tw = _text_w(draw, tag, f_sublabel)
        draw.text((px + (panel_w - tw) // 2, inner_y), tag, font=f_sublabel, fill=GREY)
        inner_y += _text_h(draw, tag, f_sublabel) + 12

        # Thin rule
        draw.rectangle([px + 18, inner_y, px + panel_w - 18, inner_y + 1], fill=cfg["color"])
        inner_y += 10

        if not pick_data:
            draw.text((px + 12, inner_y), "No pick", font=f_body, fill=GREY)
        else:
            # Pick text (wrapped, centered)
            pick_text = pick_data.get("pick", "—")
            pick_lines = _wrap(draw, pick_text.upper(), f_pick, panel_w - 16)
            for line in pick_lines[:2]:
                lw = _text_w(draw, line, f_pick)
                draw.text((px + (panel_w - lw) // 2, inner_y), line, font=f_pick, fill=WHITE)
                inner_y += _text_h(draw, line, f_pick) + 1

            inner_y += 4

            # Odds — dominant gold number
            odds_str = f"@ {pick_data.get('odds', '—')}"
            ow = _text_w(draw, odds_str, f_odds)
            draw.text((px + (panel_w - ow) // 2, inner_y), odds_str, font=f_odds, fill=GOLD)
            inner_y += _text_h(draw, odds_str, f_odds) + 6

            # Market pill
            market = pick_data.get("market", "")
            if market:
                mw = _text_w(draw, market.upper(), f_sublabel)
                draw.text((px + (panel_w - mw) // 2, inner_y), market.upper(), font=f_sublabel, fill=GREY)
                inner_y += _text_h(draw, market, f_sublabel) + 10

            # Thin rule before reasoning
            draw.rectangle([px + 18, inner_y, px + panel_w - 18, inner_y + 1], fill=(40, 55, 90))
            inner_y += 8

            # Reasoning — fill remaining space
            reasoning = pick_data.get("reasoning", "")
            reason_lines = _wrap(draw, reasoning, f_body, panel_w - 24)
            max_reason_lines = max(4, (panel_h - (inner_y - py) - 12) // (_text_h(draw, "X", f_body) + 3))
            for line in reason_lines[:max_reason_lines]:
                if inner_y + _text_h(draw, line, f_body) + 16 > py + panel_h:
                    break
                draw.text((px + 12, inner_y), line, font=f_body, fill=GREY_LIGHT)
                inner_y += _text_h(draw, line, f_body) + 3

    y = footer_top - 8

    # ── Footer ────────────────────────────────────────────────────────────────
    footer_y = SIZE - 52
    draw.rectangle([0, footer_y - 6, SIZE, footer_y - 5], fill=GOLD)

    handle = "@puntmatenz"
    hw = _text_w(draw, handle, f_footer)
    draw.text((MARGIN, footer_y), handle, font=f_footer, fill=GOLD)

    responsible = "Bet responsibly · Problem Gambling Foundation NZ: 0800 664 262"
    rw = _text_w(draw, responsible, f_footer)
    draw.text(((SIZE - rw) // 2, footer_y + 18), responsible, font=f_footer, fill=GREY)

    # Bottom gold rule
    draw.rectangle([0, SIZE - 5, SIZE, SIZE], fill=GOLD)

    return img

# ─── Public API ─────────────────────────────────────────────────────────────────

def generate_picks_images(picks, output_dir=None, date_str=None):
    """
    Generate one 1080×1080 image per match.
    Returns list of file paths.
    """
    _ensure_fonts()

    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")

    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')

    os.makedirs(output_dir, exist_ok=True)

    # Group picks by match
    matches = {}
    for p in picks:
        key = p.get("match", "unknown")
        if key not in matches:
            matches[key] = []
        matches[key].append(p)

    paths = []
    for i, (match_name, match_picks) in enumerate(matches.items()):
        img = _make_match_card(match_picks, date_str)
        fname = f"picks_{datetime.now().strftime('%Y-%m-%d')}_match{i+1}.png"
        path = os.path.join(output_dir, fname)
        img.save(path, "PNG", optimize=True)
        print(f"  ✅ Saved card: {fname}")
        paths.append(path)

    return paths


# Keep backwards-compatible alias (used by post_instagram.py and main.py)
def generate_picks_image(picks, output_path=None, date_str=None):
    """Single-image fallback: returns path to first match card."""
    paths = generate_picks_images(picks, date_str=date_str)
    if output_path and paths:
        import shutil
        shutil.copy(paths[0], output_path)
        return output_path
    return paths[0] if paths else None


if __name__ == "__main__":
    # Test with dummy picks
    test = [
        {"personality": "investor", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026 🌍", "match": "England vs DR Congo",
         "pick": "England -1.5 Goals", "market": "Handicap", "odds": "1.95",
         "reasoning": "England are a top-10 FIFA ranked side facing a DR Congo outfit with limited World Cup pedigree. At major tournament with group-stage stakes, England's attacking depth should comfortably cover a 2-goal margin."},
        {"personality": "punter", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026 🌍", "match": "England vs DR Congo",
         "pick": "Draw", "market": "Head to Head", "odds": "5.5",
         "reasoning": "England at 1.31 is a mug's bet — no value. Draw at 5.5 is outside usual range but England have a habit of making hard work of games they should cruise."},
        {"personality": "gambler", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026 🌍", "match": "England vs DR Congo",
         "pick": "DR Congo", "market": "Head to Head", "odds": "16.5",
         "reasoning": "England at a World Cup knockout stage with the weight of a nation on their shoulders? That's not a football team, that's a pressure cooker waiting to explode! At 16.5 we only need to be right once."},
    ]
    paths = generate_picks_images(test, output_dir="/tmp/puntmate_cards_test")
    print("Cards generated:", paths)
