"""
generate_carousel.py — PuntMate NZ Instagram carousel generator.
Creates 4 slides (1080x1080 each) for an Instagram carousel post:
  Slide 1: Intro/header (branding + date + sport overview)
  Slide 2: INVESTOR pick
  Slide 3: PUNTER pick
  Slide 4: GAMBLER pick

Each slide uses the "Midnight Authority" design (SVG + cairosvg).
"""

import os
import cairosvg
from datetime import datetime

GOLD  = "#C9A84B"
WHITE = "white"
NAVY  = "#060C18"

SPORT_LABELS = {
    "soccer_fifa_world_cup":  "WORLD CUP",
    "rugbyleague_nrl":        "NRL",
    "basketball_nba":         "NBA",
    "rugbyunion_super_rugby": "SUPER RUGBY",
    "tennis_atp_french_open": "ATP",
    "tennis_wta_french_open": "WTA",
}

SPORT_COLORS = {
    "soccer_fifa_world_cup":  "#1A9E5E",
    "rugbyleague_nrl":        "#CC3030",
    "basketball_nba":         "#C85520",
    "rugbyunion_super_rugby": "#CC3030",
    "tennis_atp_french_open": "#B0458A",
    "tennis_wta_french_open": "#B0458A",
}

PERSONA = {
    "investor": {"label": "INVESTOR", "tagline": "Safe. Steady. Long game.", "color": "#5AB4FF",
                 "description": "The conservative play. Low risk, steady returns, positive ROI over time.",
                 "emoji_text": "[I]", "bg_top": "#101E38", "bg_bot": "#0A1628"},
    "punter":   {"label": "PUNTER",   "tagline": "Form. Value. Gut feel.",   "color": "#C9A84B",
                 "description": "The everyday bet. Good odds, solid form, backed with a bit of NZ instinct.",
                 "emoji_text": "[P]", "bg_top": "#18140A", "bg_bot": "#100D06"},
    "gambler":  {"label": "GAMBLER",  "tagline": "Long shots. Big returns.", "color": "#FF5A6E",
                 "description": "The bold call. Chasing the upset, finding value where others won't.",
                 "emoji_text": "[G]", "bg_top": "#1C0A10", "bg_bot": "#12060A"},
}


def _esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")


def _wrap(text, max_chars):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if len(test) <= max_chars:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines


def _font(size, weight="400"):
    return f'font-family="Poppins,Lato,DejaVu Sans" font-weight="{weight}" font-size="{size}"'


def _base_svg(extra_defs=""):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="#0C1A2E"/>
    <stop offset="100%" stop-color="#060C18"/>
  </linearGradient>
  <filter id="gold_glow" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  {extra_defs}
</defs>
<rect width="1080" height="1080" fill="url(#bg)"/>
<rect x="0" y="0" width="1080" height="6" fill="{GOLD}"/>
<rect x="0" y="1074" width="1080" height="6" fill="{GOLD}"/>
'''


def _footer(slide_num, total=4):
    dots = "".join(
        f'<circle cx="{540 + (i - total//2) * 18}" cy="1040" r="{5 if i==slide_num-1 else 3}" fill="{GOLD if i==slide_num-1 else "#2A3E58"}"/>'
        for i in range(total)
    )
    return f'''
{dots}
<text x="60" y="1060" {_font(11, "700")} fill="{GOLD}" letter-spacing="1">@PUNTMATENZ</text>
<text x="1020" y="1060" text-anchor="end" {_font(10, "300")} fill="#2C4060">Swipe for picks ›</text>
'''


# ── Slide 1: Header ──────────────────────────────────────────────────────────────

def slide_intro(picks, date_str):
    sports_seen = []
    for p in picks:
        sk = p.get("sport_key", "")
        sl = SPORT_LABELS.get(sk, p.get("sport", "SPORT").split()[0])
        if sl not in sports_seen:
            sports_seen.append(sl)

    svg = _base_svg('''
  <linearGradient id="gold_line" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0%" stop-color="#C9A84B" stop-opacity="0"/>
    <stop offset="50%" stop-color="#C9A84B"/>
    <stop offset="100%" stop-color="#C9A84B" stop-opacity="0"/>
  </linearGradient>''')

    # Large PUNTMATE brand
    svg += f'''
<text x="540" y="280" text-anchor="middle" {_font(110, "900")} fill="white" letter-spacing="-3">PUNTMATE</text>
<text x="540" y="370" text-anchor="middle" {_font(80, "900")} fill="{GOLD}" letter-spacing="-2">NZ</text>

<rect x="200" y="400" width="680" height="2" fill="url(#gold_line)"/>

<text x="540" y="460" text-anchor="middle" {_font(22, "300")} fill="#6080A0" letter-spacing="4">DAILY PICKS</text>
<text x="540" y="498" text-anchor="middle" {_font(18, "400")} fill="#405060" letter-spacing="2">{_esc(date_str.upper())}</text>

<rect x="200" y="530" width="680" height="1" fill="#1A2E48"/>
'''
    # Three personality teasers
    labels = [("INVESTOR", "#5AB4FF", "[I]"), ("PUNTER", "#C9A84B", "[P]"), ("GAMBLER", "#FF5A6E", "[G]")]
    for li, (lbl, col, tag) in enumerate(labels):
        px = 200 + li * 230
        svg += f'''
<rect x="{px}" y="565" width="210" height="180" rx="14" fill="#0D1828"/>
<rect x="{px}" y="565" width="210" height="4" rx="2" fill="{col}"/>
<text x="{px+105}" y="610" text-anchor="middle" {_font(13, "800")} fill="{col}" letter-spacing="2">{_esc(lbl)}</text>
<text x="{px+105}" y="700" text-anchor="middle" {_font(42, "900")} fill="white">›</text>
'''
    svg += f'''
<text x="540" y="790" text-anchor="middle" {_font(14, "300")} fill="#304050">Three personalities. Three angles. One daily card.</text>
<text x="540" y="820" text-anchor="middle" {_font(13, "300")} fill="#263848" letter-spacing="1">SWIPE TO SEE TODAY'S PICKS</text>
'''
    svg += _footer(1)
    svg += '</svg>'
    return svg


# ── Slides 2–4: Individual pick ──────────────────────────────────────────────────

def slide_pick(pick, slide_num):
    pk   = pick.get("personality", "punter")
    cfg  = PERSONA[pk]
    col  = cfg["color"]
    sport_key   = pick.get("sport_key", "")
    sport_label = SPORT_LABELS.get(sport_key, pick.get("sport", "SPORT").split()[0].upper())
    sport_color = SPORT_COLORS.get(sport_key, GOLD)

    svg = _base_svg(f'''
  <linearGradient id="card_bg" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="{cfg["bg_top"]}"/>
    <stop offset="100%" stop-color="{cfg["bg_bot"]}"/>
  </linearGradient>''')

    # Card panel
    svg += f'''
<rect x="50" y="90" width="980" height="870" rx="24" fill="url(#card_bg)"/>
<rect x="50" y="90" width="6" height="870" rx="3" fill="{col}"/>
'''
    # Persona header
    svg += f'''
<text x="100" y="150" {_font(18, "800")} fill="{col}" letter-spacing="3">{_esc(cfg["label"])}</text>
<text x="100" y="178" {_font(13, "300")} fill="#506080">{_esc(cfg["tagline"])}</text>
<line x1="100" y1="198" x2="980" y2="198" stroke="#1C2E48" stroke-width="1"/>
'''
    # Sport badge + match
    badge_w = len(sport_label) * 7 + 24
    svg += f'''
<rect x="100" y="215" width="{badge_w}" height="24" rx="12" fill="{sport_color}"/>
<text x="{100 + badge_w//2}" y="232" text-anchor="middle" {_font(11, "700")} fill="white" letter-spacing="1">{_esc(sport_label)}</text>
<text x="{100 + badge_w + 16}" y="234" {_font(15, "600")} fill="#A0B8CC">{_esc(pick.get("match", ""))}</text>
'''
    # Big pick text
    pick_str  = pick.get("pick", "—").upper()
    pick_font = 96 if len(pick_str) <= 10 else 72 if len(pick_str) <= 14 else 56 if len(pick_str) <= 18 else 44
    svg += f'''
<text x="540" y="{340 if pick_font >= 72 else 360}" text-anchor="middle"
  {_font(pick_font, "900")} fill="white" letter-spacing="-2">{_esc(pick_str)}</text>
'''
    # Gold odds (hero element)
    odds_str = f"@ {pick.get('odds', '—')}"
    svg += f'''
<text x="540" y="520" text-anchor="middle" {_font(120, "900")} fill="{GOLD}"
  filter="url(#gold_glow)">{_esc(odds_str)}</text>
<text x="540" y="570" text-anchor="middle" {_font(13, "400")} fill="#2A4060" letter-spacing="3">{_esc(pick.get("market","").upper())}</text>

<line x1="100" y1="596" x2="980" y2="596" stroke="#1C2E48" stroke-width="1"/>
'''
    # Reasoning
    rlines = _wrap(pick.get("reasoning", ""), 62)
    for li, rline in enumerate(rlines[:4]):
        ry = 634 + li * 30
        svg += f'<text x="540" y="{ry}" text-anchor="middle" {_font(17, "400")} fill="#6080A0">{_esc(rline)}</text>\n'

    # Confidence
    conf = pick.get("confidence", "Medium").upper()
    conf_color = {"HIGH": "#4CAF50", "MEDIUM": "#FFC107", "LOW": "#FF5722"}.get(conf, "#304050")
    svg += f'''
<text x="540" y="790" text-anchor="middle" {_font(12, "600")} fill="{conf_color}" letter-spacing="3">CONFIDENCE: {_esc(conf)}</text>
'''
    svg += _footer(slide_num)
    svg += '</svg>'
    return svg


# ── Public API ────────────────────────────────────────────────────────────────────

def generate_carousel_slides(picks, output_dir=None, date_str=None):
    """
    Generate 4 carousel slides (intro + one per personality).
    Returns list of 4 file paths.
    """
    if not date_str:
        date_str = datetime.now().strftime("%-d %B %Y")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'cards')
    os.makedirs(output_dir, exist_ok=True)

    date_slug = datetime.now().strftime('%Y-%m-%d')
    paths = []

    # Slide 1: intro
    svg = slide_intro(picks, date_str)
    path = os.path.join(output_dir, f"carousel_{date_slug}_1_intro.png")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=1080, output_height=1080)
    print(f"  ✅ Slide 1: intro")
    paths.append(path)

    # Slides 2–4: one per personality
    grouped = {p.get("personality"): p for p in picks}
    for i, pk in enumerate(["investor", "punter", "gambler"], start=2):
        pick = grouped.get(pk, {})
        if not pick:
            continue
        svg = slide_pick(pick, i)
        path = os.path.join(output_dir, f"carousel_{date_slug}_{i}_{pk}.png")
        cairosvg.svg2png(bytestring=svg.encode(), write_to=path, output_width=1080, output_height=1080)
        print(f"  ✅ Slide {i}: {pk}")
        paths.append(path)

    return paths


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
    paths = generate_carousel_slides(test_picks, output_dir="/tmp/puntmate_carousel_test")
    print("Generated:", paths)
