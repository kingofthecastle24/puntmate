"""
generate_picks_image.py — PuntMate NZ daily picks card generator.
Creates one 1080x1080 PNG showing the day's three best picks (Investor/Punter/Gambler).

Design: "Midnight Authority" — dark navy, surgical gold accents, Poppins typography.
Uses SVG + cairosvg for crisp, professional output. No custom font downloads required
(uses system Poppins/Lato fonts available in GitHub Actions ubuntu-latest).
"""

import os
import cairosvg
from datetime import datetime


# ── Brand config ────────────────────────────────────────────────────────────────
GOLD       = "#C9A84B"
GOLD_LIGHT = "#E0C070"
WHITE      = "white"
NAVY_BG    = "#060C18"
NAVY_MID   = "#0C1A2E"

PERSONA_CONFIG = {
    "investor": {"label": "INVESTOR", "tagline": "Safe · Steady · Long game",  "color": "#5AB4FF", "row_grad": "row_inv"},
    "punter":   {"label": "PUNTER",   "tagline": "Form · Value · Gut feel",    "color": "#C9A84B", "row_grad": "row_pun"},
    "gambler":  {"label": "GAMBLER",  "tagline": "Long shots · Big returns",   "color": "#FF5A6E", "row_grad": "row_gam"},
}

SPORT_LABELS = {
    "soccer_fifa_world_cup":     "WORLD CUP",
    "rugbyleague_nrl":           "NRL",
    "basketball_nba":            "NBA",
    "rugbyunion_super_rugby":    "SUPER RUGBY",
    "tennis_atp_french_open":    "ATP",
    "tennis_wta_french_open":    "WTA",
}

SPORT_COLORS = {
    "soccer_fifa_world_cup":     "#1A9E5E",
    "rugbyleague_nrl":           "#CC3030",
    "basketball_nba":            "#C85520",
    "rugbyunion_super_rugby":    "#CC3030",
    "tennis_atp_french_open":    "#B0458A",
    "tennis_wta_french_open":    "#B0458A",
}

CONF_COLORS = {
    "High":   ["#4CAF50", "#4CAF50", "#4CAF50"],
    "Medium": ["#FFC107", "#FFC107", "#1C2E48"],
    "Low":    ["#FF5722", "#1C2E48", "#1C2E48"],
    "HIGH":   ["#4CAF50", "#4CAF50", "#4CAF50"],
    "MEDIUM": ["#FFC107", "#FFC107", "#1C2E48"],
    "LOW":    ["#FF5722", "#1C2E48", "#1C2E48"],
}


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap(text, max_chars):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= max_chars:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _build_svg(picks, date_str):
    W, H   = 1080, 1080
    MARGIN = 48
    INNER  = W - MARGIN * 2  # 984

    # Column layout
    COL_LEFT    = 200
    GAP         = 16
    SEP_W       = 1
    COL_PICK    = 240
    SEP1_X      = MARGIN + COL_LEFT + GAP
    SEP2_X      = SEP1_X + SEP_W + GAP + COL_PICK + GAP
    PICK_CX     = SEP1_X + SEP_W + GAP + COL_PICK // 2
    REASON_X    = SEP2_X + GAP
    REASON_W    = W - MARGIN - REASON_X

    HEADER_H    = 106
    FOOTER_H    = 50
    ROW_TOP     = HEADER_H + 8
    ROW_AREA    = H - ROW_TOP - FOOTER_H - 8
    ROW_GAP     = 10
    ROW_H       = (ROW_AREA - ROW_GAP * 2) // 3

    svg = [f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{NAVY_MID}"/>
    <stop offset="100%" stop-color="{NAVY_BG}"/>
  </linearGradient>
  <linearGradient id="row_inv" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#101E38"/><stop offset="100%" stop-color="#0C1830"/>
  </linearGradient>
  <linearGradient id="row_pun" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#18140A"/><stop offset="100%" stop-color="#110D06"/>
  </linearGradient>
  <linearGradient id="row_gam" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#1C0A10"/><stop offset="100%" stop-color="#12060A"/>
  </linearGradient>
  <filter id="gold_glow" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<rect x="0" y="0" width="{W}" height="5" fill="{GOLD}"/>

<!-- Header -->
<text x="{MARGIN}" y="68" font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="54"
  fill="white" letter-spacing="-1">PUNTMATE</text>
<text x="{MARGIN+320}" y="68" font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="54"
  fill="{GOLD}" letter-spacing="-1"> NZ</text>
<text x="{W-MARGIN}" y="46" text-anchor="end" font-family="Poppins,Lato,DejaVu Sans" font-weight="400"
  font-size="12" fill="#50708A" letter-spacing="2">{_esc(date_str.upper())}</text>
<text x="{W-MARGIN}" y="66" text-anchor="end" font-family="Poppins,Lato,DejaVu Sans" font-weight="300"
  font-size="11" fill="#304050" letter-spacing="1">THREE PICKS · ONE DAILY CARD</text>
<line x1="{MARGIN}" y1="90" x2="{W-MARGIN}" y2="90" stroke="{GOLD}" stroke-width="1.5" opacity="0.5"/>
''']

    # Group picks by personality
    grouped = {p.get("personality", "punter"): p for p in picks}

    for i, pk in enumerate(["investor", "punter", "gambler"]):
        pick = grouped.get(pk, {})
        cfg  = PERSONA_CONFIG[pk]
        ry   = ROW_TOP + i * (ROW_H + ROW_GAP)
        rx   = MARGIN
        col  = cfg["color"]
        rg   = cfg["row_grad"]

        # Panel
        svg.append(f'''
<rect x="{rx}" y="{ry}" width="{INNER}" height="{ROW_H}" rx="13" fill="url(#{rg})"/>
<rect x="{rx}" y="{ry+18}" width="5" height="{ROW_H-36}" rx="2.5" fill="{col}"/>
''')

        lx = rx + 18

        # Persona label + tagline
        svg.append(f'''
<text x="{lx}" y="{ry+34}" font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="16"
  fill="{col}" letter-spacing="2">{_esc(cfg["label"])}</text>
<text x="{lx}" y="{ry+52}" font-family="Poppins,Lato,DejaVu Sans" font-weight="300" font-size="10.5"
  fill="#506080">{_esc(cfg["tagline"])}</text>
''')

        if pick:
            sport_key   = pick.get("sport_key", "")
            sport_label = SPORT_LABELS.get(sport_key, pick.get("sport", "SPORT").split()[0].upper())
            sport_color = SPORT_COLORS.get(sport_key, GOLD)

            # Sport badge
            badge_w = min(len(sport_label) * 7 + 20, 110)
            svg.append(f'''
<rect x="{lx}" y="{ry+60}" width="{badge_w}" height="19" rx="9.5" fill="{sport_color}"/>
<text x="{lx + badge_w//2}" y="{ry+73}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="700" font-size="9.5"
  fill="white" letter-spacing="1">{_esc(sport_label)}</text>
''')

            # Match name
            match_name = pick.get("match", "")
            words = match_name.split()
            half = max(1, len(words) // 2)
            m1, m2 = " ".join(words[:half]), " ".join(words[half:])
            svg.append(f'''
<text x="{lx}" y="{ry+96}" font-family="Poppins,Lato,DejaVu Sans" font-weight="600" font-size="12"
  fill="#A0B8CC">{_esc(m1)}</text>
<text x="{lx}" y="{ry+112}" font-family="Poppins,Lato,DejaVu Sans" font-weight="600" font-size="12"
  fill="#A0B8CC">{_esc(m2)}</text>
''')

            # Confidence dots
            conf = pick.get("confidence", "Medium")
            dot_cols = CONF_COLORS.get(conf, ["#304050", "#304050", "#304050"])
            dot_y = ry + ROW_H - 20
            for di, dc in enumerate(dot_cols):
                svg.append(f'<circle cx="{lx + di*12}" cy="{dot_y}" r="4" fill="{dc}"/>')
            svg.append(f'<text x="{lx+42}" y="{dot_y+5}" font-family="Poppins,Lato,DejaVu Sans" '
                       f'font-size="10" font-weight="500" fill="#304050">{_esc(conf.upper())}</text>')

        # Separator 1
        svg.append(f'<line x1="{SEP1_X}" y1="{ry+16}" x2="{SEP1_X}" y2="{ry+ROW_H-16}" stroke="#1C2E48" stroke-width="1"/>')

        # ── Centre: pick + odds ──────────────────────────────────────────────
        if pick:
            pick_str = pick.get("pick", "—").upper()
            pick_words = pick_str.split()

            # Auto-size font
            pick_font = 36
            est_w = len(pick_str) * pick_font * 0.55
            if est_w > COL_PICK - 10:
                pick_font = max(20, int((COL_PICK - 10) / max(1, len(pick_str) * 0.55)))

            needs_wrap = len(pick_str) * pick_font * 0.55 > COL_PICK - 8 and len(pick_words) > 1
            if needs_wrap:
                mid = len(pick_words) // 2
                pl1, pl2 = " ".join(pick_words[:mid]), " ".join(pick_words[mid:])
                svg.append(f'''
<text x="{PICK_CX}" y="{ry+46}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="{pick_font}"
  fill="white">{_esc(pl1)}</text>
<text x="{PICK_CX}" y="{ry+46+pick_font+4}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="{pick_font}"
  fill="white">{_esc(pl2)}</text>
''')
                odds_top = ry + 46 + (pick_font + 4) * 2 + 10
            else:
                svg.append(f'''
<text x="{PICK_CX}" y="{ry+54}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="800" font-size="{pick_font}"
  fill="white">{_esc(pick_str)}</text>
''')
                odds_top = ry + 54 + pick_font + 10

            svg.append(f'<line x1="{SEP1_X+GAP+SEP_W}" y1="{odds_top-4}" x2="{SEP2_X-GAP}" y2="{odds_top-4}" stroke="#1C2E48" stroke-width="1"/>')

            odds_str = f"@ {pick.get('odds', '—')}"
            odds_font = 64
            svg.append(f'''
<text x="{PICK_CX}" y="{odds_top + odds_font - 8}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="900" font-size="{odds_font}"
  fill="{GOLD}" filter="url(#gold_glow)">{_esc(odds_str)}</text>
<text x="{PICK_CX}" y="{ry+ROW_H-18}" text-anchor="middle"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="400" font-size="10"
  fill="#2C4060" letter-spacing="2">{_esc(pick.get("market", "").upper())}</text>
''')

        # Separator 2
        svg.append(f'<line x1="{SEP2_X}" y1="{ry+16}" x2="{SEP2_X}" y2="{ry+ROW_H-16}" stroke="#1C2E48" stroke-width="1"/>')

        # ── Right: reasoning ─────────────────────────────────────────────────
        if pick:
            reasoning = pick.get("reasoning", "")
            chars = max(20, int(REASON_W / (11.5 * 0.53)))
            rlines = _wrap(reasoning, chars)
            line_h = 17
            total_h = len(rlines[:6]) * line_h
            start_y = ry + (ROW_H - total_h) // 2 + 14

            for li, rline in enumerate(rlines[:6]):
                ly = start_y + li * line_h
                if ly + line_h > ry + ROW_H - 12:
                    break
                svg.append(f'''<text x="{REASON_X}" y="{ly}"
  font-family="Poppins,Lato,DejaVu Sans" font-weight="400" font-size="11.5"
  fill="#7090B0">{_esc(rline)}</text>''')

    # Footer
    fy = H - FOOTER_H
    svg.append(f'''
<line x1="0" y1="{fy+2}" x2="{W}" y2="{fy+2}" stroke="{GOLD}" stroke-width="1" opacity="0.35"/>
<text x="{MARGIN}" y="{fy+28}" font-family="Poppins,Lato,DejaVu Sans" font-weight="700"
  font-size="12" fill="{GOLD}" letter-spacing="1">@PUNTMATENZ</text>
<text x="{W//2}" y="{fy+28}" text-anchor="middle" font-family="Poppins,Lato,DejaVu Sans"
  font-weight="300" font-size="10.5" fill="#2C4060">Bet responsibly  ·  Problem Gambling Foundation NZ: 0800 664 262</text>
<text x="{W-MARGIN}" y="{fy+28}" text-anchor="end" font-family="Poppins,Lato,DejaVu Sans"
  font-weight="500" font-size="11" fill="#304050">Join on WhatsApp</text>
<rect x="0" y="{H-5}" width="{W}" height="5" fill="{GOLD}"/>
</svg>''')

    return "".join(svg)


# ── Public API ────────────────────────────────────────────────────────────────────

def generate_picks_images(picks, output_dir=None, date_str=None):
    """
    Generate one 1080x1080 daily picks card (three personality rows).
    Returns list with a single file path.
    """
    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')
    os.makedirs(output_dir, exist_ok=True)

    svg_content = _build_svg(picks, date_str)
    fname = f"picks_{datetime.now().strftime('%Y-%m-%d')}.png"
    path  = os.path.join(output_dir, fname)

    cairosvg.svg2png(
        bytestring=svg_content.encode(),
        write_to=path,
        output_width=1080,
        output_height=1080,
    )
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
         "reasoning": "England are a top-10 FIFA ranked side facing DR Congo with limited World Cup pedigree. Group-stage pressure favours the favourite covering two goals comfortably.",
         "confidence": "High"},
        {"personality": "punter", "sport_key": "rugbyleague_nrl",
         "sport": "NRL", "match": "Melbourne Storm vs Parramatta Eels",
         "pick": "Melbourne Storm", "market": "Head to Head", "odds": "2.10",
         "reasoning": "Storm at home is always a banker. Parramatta have been inconsistent and Melbourne's defence is the best in the comp right now. Good value at $2.10.",
         "confidence": "High"},
        {"personality": "gambler", "sport_key": "soccer_fifa_world_cup",
         "sport": "FIFA World Cup 2026", "match": "Belgium vs Senegal",
         "pick": "Senegal", "market": "Head to Head", "odds": "4.30",
         "reasoning": "Belgium's golden generation is rusty and Senegal showed serious hunger in qualifying. Africa's champion with chips on their shoulder — value at 4.30 all day.",
         "confidence": "Low"},
    ]
    paths = generate_picks_images(test_picks, output_dir="/tmp/puntmate_test")
    print("Generated:", paths)
