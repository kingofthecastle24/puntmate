"""
generate_picks_image.py — Creates an Instagram-ready picks card image (1080x1080px)
Auric Edge design: dark navy + gold, three personality columns.
Requires: Pillow (pip install Pillow)
"""

from PIL import Image, ImageDraw, ImageFont
import os
import textwrap
from datetime import datetime

# --- Colours ---
NAVY   = (9, 13, 28)       # #090D1C
GOLD   = (201, 168, 75)    # #C9A84B
WHITE  = (255, 255, 255)
GREY   = (160, 165, 180)
PANEL  = (18, 24, 48)      # slightly lighter panel bg

SIZE   = 1080
MARGIN = 40

PERSONALITY_CONFIG = {
    "investor": {"label": "INVESTOR", "emoji": "📊", "tagline": "Safe. Steady. Surgical."},
    "punter":   {"label": "PUNTER",   "emoji": "🎯", "tagline": "Back the form. Trust your gut."},
    "gambler":  {"label": "GAMBLER",  "emoji": "🎰", "tagline": "Big odds. No regrets."},
}


def _load_font(size, bold=False):
    """Load a font — falls back to default if custom fonts not available."""
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_text_centered(draw, text, y, font, color, width=SIZE):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (width - w) // 2
    draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]  # return height


def _wrap_text(text, font, max_width, draw):
    """Wrap text to fit within max_width pixels."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def generate_picks_image(picks, output_path=None, date_str=None):
    """
    Generate a 1080x1080 Instagram picks card from a list of pick dicts.
    Each pick must have: personality, sport, match, pick, odds, reasoning
    Returns the output path.
    """
    if not date_str:
        date_str = datetime.now().strftime("%A %-d %B %Y").upper()

    if not output_path:
        output_path = os.path.join(
            os.path.dirname(__file__), '..', 'data',
            f"picks_card_{datetime.now().strftime('%Y-%m-%d')}.png"
        )

    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # --- Fonts ---
    f_title   = _load_font(52, bold=True)
    f_date    = _load_font(22)
    f_persona = _load_font(28, bold=True)
    f_tagline = _load_font(18)
    f_sport   = _load_font(16)
    f_pick    = _load_font(22, bold=True)
    f_odds    = _load_font(20)
    f_reason  = _load_font(15)
    f_footer  = _load_font(14)

    # --- Gold top bar ---
    draw.rectangle([0, 0, SIZE, 6], fill=GOLD)

    # --- Header ---
    y = 28
    h = _draw_text_centered(draw, "PUNTMATE NZ", y, f_title, WHITE)
    y += h + 6
    h = _draw_text_centered(draw, date_str, y, f_date, GOLD)
    y += h + 14

    # --- Gold divider ---
    draw.rectangle([MARGIN, y, SIZE - MARGIN, y + 2], fill=GOLD)
    y += 14

    # --- Three personality columns ---
    col_count = 3
    col_w = (SIZE - MARGIN * 2 - 16) // col_count  # 16px total gaps
    col_gap = 8
    col_top = y
    col_bottom = SIZE - 90  # leave room for footer

    for col_idx, persona_key in enumerate(["investor", "punter", "gambler"]):
        cfg = PERSONALITY_CONFIG[persona_key]
        col_picks = [p for p in picks if p.get("personality") == persona_key]

        col_x = MARGIN + col_idx * (col_w + col_gap)
        col_h = col_bottom - col_top

        # Panel background
        draw.rectangle([col_x, col_top, col_x + col_w, col_top + col_h], fill=PANEL)

        # Gold top accent for column
        draw.rectangle([col_x, col_top, col_x + col_w, col_top + 3], fill=GOLD)

        cy = col_top + 12

        # Emoji + Label
        label_text = f"{cfg['emoji']} {cfg['label']}"
        bbox = draw.textbbox((0, 0), label_text, font=f_persona)
        lw = bbox[2] - bbox[0]
        draw.text((col_x + (col_w - lw) // 2, cy), label_text, font=f_persona, fill=GOLD)
        cy += (bbox[3] - bbox[1]) + 4

        # Tagline
        bbox = draw.textbbox((0, 0), cfg['tagline'], font=f_tagline)
        tw = bbox[2] - bbox[0]
        draw.text((col_x + (col_w - tw) // 2, cy), cfg['tagline'], font=f_tagline, fill=GREY)
        cy += (bbox[3] - bbox[1]) + 8

        # Divider inside column
        draw.rectangle([col_x + 8, cy, col_x + col_w - 8, cy + 1], fill=GOLD)
        cy += 9

        if not col_picks:
            no_text = "No picks today"
            bbox = draw.textbbox((0, 0), no_text, font=f_sport)
            draw.text((col_x + (col_w - (bbox[2]-bbox[0])) // 2, cy), no_text, font=f_sport, fill=GREY)
        else:
            for pick in col_picks:
                if cy > col_bottom - 60:
                    break  # ran out of space

                # Sport label
                sport = pick.get("sport", "")
                bbox = draw.textbbox((0, 0), sport, font=f_sport)
                sw = bbox[2] - bbox[0]
                draw.text((col_x + (col_w - sw) // 2, cy), sport, font=f_sport, fill=GREY)
                cy += (bbox[3] - bbox[1]) + 3

                # Match (wrapped)
                match = pick.get("match", "")
                match_lines = _wrap_text(match, f_sport, col_w - 12, draw)
                for line in match_lines[:2]:
                    bbox = draw.textbbox((0, 0), line, font=f_sport)
                    lw = bbox[2] - bbox[0]
                    draw.text((col_x + (col_w - lw) // 2, cy), line, font=f_sport, fill=WHITE)
                    cy += (bbox[3] - bbox[1]) + 2

                # Pick + odds
                pick_text = f"► {pick.get('pick', '')} @ {pick.get('odds', '')}"
                pick_lines = _wrap_text(pick_text, f_pick, col_w - 12, draw)
                for line in pick_lines[:2]:
                    bbox = draw.textbbox((0, 0), line, font=f_pick)
                    lw = bbox[2] - bbox[0]
                    draw.text((col_x + (col_w - lw) // 2, cy), line, font=f_pick, fill=GOLD)
                    cy += (bbox[3] - bbox[1]) + 2

                # Short reasoning (max 2 lines)
                reason = pick.get("reasoning", "")
                reason_lines = _wrap_text(reason, f_reason, col_w - 12, draw)
                for line in reason_lines[:3]:
                    bbox = draw.textbbox((0, 0), line, font=f_reason)
                    draw.text((col_x + 6, cy), line, font=f_reason, fill=GREY)
                    cy += (bbox[3] - bbox[1]) + 1

                cy += 8
                # Mini divider between picks
                if pick != col_picks[-1]:
                    draw.rectangle([col_x + 12, cy, col_x + col_w - 12, cy + 1], fill=(40, 50, 80))
                    cy += 5

    # --- Footer ---
    footer_y = col_bottom + 10
    draw.rectangle([0, footer_y - 4, SIZE, footer_y - 3], fill=GOLD)

    footer_text = "⚠️ Bet responsibly · Problem Gambling Foundation NZ: 0800 664 262 · @puntmatenz"
    bbox = draw.textbbox((0, 0), footer_text, font=f_footer)
    fw = bbox[2] - bbox[0]
    if fw > SIZE - MARGIN * 2:
        # Split into two lines
        lines = [
            "⚠️ Bet responsibly · Problem Gambling Foundation NZ: 0800 664 262",
            "@puntmatenz"
        ]
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=f_footer)
            lw = bbox[2] - bbox[0]
            draw.text(((SIZE - lw) // 2, footer_y + i * 18), line, font=f_footer, fill=GREY)
    else:
        draw.text(((SIZE - fw) // 2, footer_y), footer_text, font=f_footer, fill=GREY)

    # --- Gold bottom bar ---
    draw.rectangle([0, SIZE - 6, SIZE, SIZE], fill=GOLD)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, "PNG", quality=95)
    print(f"  Saved picks card: {output_path}")
    return output_path


if __name__ == "__main__":
    # Test with dummy picks
    test_picks = [
        {"personality": "investor", "sport": "NRL 🏉", "match": "Warriors vs Broncos",
         "pick": "Warriors -1.5", "odds": "1.85", "reasoning": "Warriors strong at home last 5 games, Broncos missing key forward."},
        {"personality": "punter", "sport": "NRL 🏉", "match": "Warriors vs Broncos",
         "pick": "Over 42.5 Points", "odds": "2.10", "reasoning": "Both teams averaging 24+ pts in last month. Should be high scorer."},
        {"personality": "gambler", "sport": "NRL 🏉", "match": "Warriors vs Broncos",
         "pick": "Broncos to Win", "odds": "3.20", "reasoning": "Broncos have upset Warriors 3 times in last 5 away games. Value here."},
        {"personality": "investor", "sport": "FIFA World Cup 2026 🌍", "match": "France vs Mexico",
         "pick": "France to Win", "odds": "1.55", "reasoning": "France dominant in form, Mexico inconsistent in last 3."},
        {"personality": "punter", "sport": "FIFA World Cup 2026 🌍", "match": "France vs Mexico",
         "pick": "Both Teams to Score", "odds": "1.95", "reasoning": "Mexico always fights back. France concedes too."},
        {"personality": "gambler", "sport": "FIFA World Cup 2026 🌍", "match": "France vs Mexico",
         "pick": "Mexico to Win", "odds": "4.50", "reasoning": "Mexico shocked France in 2018 World Cup. History can repeat."},
    ]
    out = generate_picks_image(test_picks, output_path="/tmp/test_picks_card.png")
    print(f"Test card saved to {out}")
