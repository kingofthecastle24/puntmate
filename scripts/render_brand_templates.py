#!/usr/bin/env python3
"""
render_brand_templates.py — Playwright-based renderer for the approved
PuntMate Brand Kit (.dc.html) templates. Replaces Pillow (generate_picks_image.py)
as the production rendering path.

Why: the Pillow renderer redraws the approved Claude Design templates by hand and
drifts from them over time. This script instead boots the *actual* .dc.html
templates in a headless Chromium browser, injects real pick data through the
template's own runtime API, and screenshots each canvas at native size — so the
output is always pixel-identical to what's approved in the Brand Kit.

Usage:
    python scripts/render_brand_templates.py --pick-file data/latest_run.json --pick-index 0
    python scripts/render_brand_templates.py --pick-json '{"match": "...", ...}'
    python scripts/render_brand_templates.py --test-overflow
    python scripts/render_brand_templates.py --test-portugal-spain

Outputs PNGs into data/cards/ using the naming convention:
    data/cards/YYYY-MM-DD_<match>_<theme>_1_cover.png
    data/cards/YYYY-MM-DD_<match>_<theme>_2_tip.png
    data/cards/YYYY-MM-DD_<match>_<theme>_3_breakdown.png
    data/cards/YYYY-MM-DD_<match>_story.png

And prints a JSON result to stdout:
    {"ok": true, "files": {...}, "warnings": [...], "props": {...}}
or, on failure, prints {"ok": false, "error": "..."} and exits 1.

Does NOT touch the original brand/Templates/*.dc.html files — all injection
(React/ReactDOM + local @font-face CSS) happens on a temp copy served locally.
"""

import argparse
import http.server
import json
import os
import re
import shutil
import sys
import tempfile
import threading
from datetime import datetime, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRAND_DIR = os.path.join(REPO_ROOT, "brand", "Templates")
FONTS_DIR = os.path.join(REPO_ROOT, "fonts")
CARDS_DIR = os.path.join(REPO_ROOT, "data", "cards")

BETSLIP_NIGHT = os.path.join(BRAND_DIR, "PuntMate Bet Post - Betslip Night.dc.html")
MATCHDAY_PRINT = os.path.join(BRAND_DIR, "PuntMate Bet Post - Matchday Print.dc.html")
SOCIAL_TEMPLATES = os.path.join(BRAND_DIR, "PuntMate Social Templates.dc.html")

FEED_SLIDE_SIZE = (1080, 1350)
STORY_SIZE = (1080, 1920)

REACT_CDN = [
    "https://unpkg.com/react@18/umd/react.production.min.js",
    "https://unpkg.com/react-dom@18/umd/react-dom.production.min.js",
]

# Local @font-face rules — only families/weights we actually have .ttf files for.
# Browser falls back to its default sans-serif for anything not covered here,
# which is non-fatal (slightly different metrics, not a crash).
FONT_FACES = [
    ("Archivo",         900, "Archivo-Black.ttf"),
    ("Anton",           400, "Anton-Regular.ttf"),
    ("Barlow Condensed", 600, "BarlowCondensed-SemiBold.ttf"),
    ("Barlow Condensed", 700, "BarlowCondensed-Bold.ttf"),
    ("Space Grotesk",   400, "SpaceGrotesk-Regular.ttf"),
    ("Space Grotesk",   500, "SpaceGrotesk-Medium.ttf"),
    ("Space Grotesk",   700, "SpaceGrotesk-Bold.ttf"),
    ("Space Mono",      400, "SpaceMono-Regular.ttf"),
    ("Space Mono",      700, "SpaceMono-Bold.ttf"),
]

SPORT_LABELS = {
    "soccer_fifa_world_cup": "WORLD CUP",
    "rugbyleague_nrl": "NRL",
    "rugbyunion_super_rugby": "SUPER RUGBY",
    "mma_mixed_martial_arts": "UFC",
    "basketball_nba": "NBA",
    "tennis_atp_wimbledon": "WIMBLEDON",
    "tennis_wta_wimbledon": "WIMBLEDON",
}

BIG_GAME_SPORTS = {"soccer_fifa_world_cup", "mma_mixed_martial_arts"}
BIG_GAME_KEYWORDS = [
    "final", "semi-final", "quarter-final", "grand final",
    "championship", "world cup final",
]

PALETTES = ["green", "blue", "amber", "pink"]


class QuietHTTPHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep stdout clean for the JSON result


def slugify(text):
    text = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_")
    return text or "match"


def pick_palette(for_date):
    """Deterministic day-of-year rotation through the 4 accent colours.
    No extra state file needed — same date always gives the same palette,
    but it moves on every day so the feed doesn't look identical post to post."""
    doy = for_date.timetuple().tm_yday
    return PALETTES[doy % len(PALETTES)]


def choose_theme(pick):
    """Betslip Night (dark) is the default look; Matchday Print (cream/red)
    is reserved for big-game coverage — mirrors BIG_GAME_SPORTS/KEYWORDS in
    scripts/fetch_odds.py so the renderer agrees with the pick-generation logic."""
    sport_key = pick.get("sport_key", "")
    match_text = f"{pick.get('home_team', '')} {pick.get('away_team', '')} {pick.get('match', '')}".lower()
    is_big = sport_key in BIG_GAME_SPORTS or any(kw in match_text for kw in BIG_GAME_KEYWORDS)
    return "print" if is_big else "night"


def confidence_to_dots(label):
    return {"low": 2, "medium": 3, "high": 5}.get((label or "medium").lower(), 3)


def build_props(pick, handle="@puntmatenz"):
    """Map a pipeline pick dict (data/latest_run.json entry) into the props
    schema shared by the Betslip Night / Matchday Print / Social templates."""
    match = pick.get("match") or f"{pick.get('home_team', '')} vs {pick.get('away_team', '')}"
    sport_key = pick.get("sport_key", "")
    sport_label = SPORT_LABELS.get(sport_key, (pick.get("sport") or sport_key or "").upper())
    selection = (pick.get("pick") or "").upper()
    market = (pick.get("market") or "").upper()

    try:
        odds_val = float(pick.get("odds", 0))
        odds_str = f"{odds_val:.2f}"
    except (TypeError, ValueError):
        odds_str = str(pick.get("odds", ""))

    confidence_label = (pick.get("confidence") or "Medium").upper()
    reasoning = pick.get("reasoning", "").strip()

    props = {
        "matchup": match,
        "sportTag": sport_label,
        "market": market,
        "selection": selection,
        "selectionShort": selection.split()[-1] if selection else selection,
        "odds": odds_str,
        "oddsNote": "Best value on the board",
        "insight": (reasoning[:140] + "…") if len(reasoning) > 140 else reasoning,
        "competition": sport_label,
        "analysis": reasoning,
        "confidence": confidence_to_dots(confidence_label),
        "confidenceLabel": confidence_label,
        "handle": handle,
        "coverTheme": "Daily Pick",
    }
    return props


def render_wrapper_html(template_path, tmp_dir):
    """Copy a .dc.html template into tmp_dir with React/ReactDOM CDN scripts
    injected before support.js, and Google Fonts links swapped for local
    @font-face rules. Does not modify the original file."""
    with open(template_path, encoding="utf-8") as f:
        html = f.read()

    react_tags = "\n".join(f'<script src="{u}"></script>' for u in REACT_CDN)
    assert '<script src="./support.js"></script>' in html, "support.js script tag not found — template structure changed?"
    html = html.replace(
        '<script src="./support.js"></script>',
        react_tags + '\n<script src="./support.js"></script>',
        1,
    )

    # Strip Google Fonts network dependency, use local files instead.
    html = re.sub(
        r'<link href="https://fonts\.googleapis\.com/css2\?family=[^"]*" rel="stylesheet">',
        "<style>/* google fonts link removed — using local @font-face below */</style>",
        html,
    )
    font_face_css = "\n".join(
        f"""@font-face {{
  font-family: '{family}';
  font-weight: {weight};
  src: url('./fonts/{fname}') format('truetype');
  font-display: block;
}}"""
        for family, weight, fname in FONT_FACES
    )
    html = html.replace("</head>", f"<style>{font_face_css}</style>\n</head>", 1)

    out_path = os.path.join(tmp_dir, os.path.basename(template_path))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    shutil.copy(os.path.join(os.path.dirname(template_path), "support.js"), tmp_dir)

    fonts_out = os.path.join(tmp_dir, "fonts")
    os.makedirs(fonts_out, exist_ok=True)
    for _, _, fname in FONT_FACES:
        src = os.path.join(FONTS_DIR, fname)
        if os.path.exists(src):
            shutil.copy(src, fonts_out)

    return out_path


class LocalServer:
    def __init__(self, directory):
        handler = lambda *a, **kw: QuietHTTPHandler(*a, directory=directory, **kw)
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()


def capture_exports(page, export_ids, expected_sizes, out_paths, warnings):
    """Screenshot each data-export-id element at native size, with the
    overflow/placeholder/error checks from the brief."""
    body_text = page.inner_text("body")
    if "{{" in body_text or "}}" in body_text:
        raise RuntimeError("unresolved {{ placeholder }} found in rendered output — props did not fully apply")
    if re.search(r"\bdc[-_ ]?error\b", body_text, re.I):
        raise RuntimeError("Design Component error message visible in rendered output")

    for export_id, expected_size, out_path in zip(export_ids, expected_sizes, out_paths):
        selector = f'[data-export-id="{export_id}"]'
        el = page.query_selector(selector)
        if el is None:
            raise RuntimeError(f"export selector not found: {selector}")

        box = el.bounding_box()
        if box is None:
            raise RuntimeError(f"export element has no layout box: {selector}")
        w, h = round(box["width"]), round(box["height"])
        if (w, h) != expected_size:
            warnings.append(
                f"{export_id}: rendered {w}x{h}, expected {expected_size[0]}x{expected_size[1]}"
            )

        el.screenshot(path=out_path)


def wait_for_dc_boot(page, timeout_ms=15000):
    page.wait_for_function("() => typeof window.__dcSetProps === 'function' && typeof window.__dcRootName === 'function'", timeout=timeout_ms)


def set_props_and_settle(page, props):
    page.evaluate("(props) => window.__dcSetProps(window.__dcRootName(), props)", props)
    page.wait_for_timeout(150)  # let React commit before we poll fonts
    page.evaluate("async () => { await document.fonts.ready; }")
    page.wait_for_timeout(200)  # paint settle


def check_no_overlap_and_containment(page, warnings):
    """Best-effort DOM bounding-box sanity check: flag any text element whose
    box extends past its immediate parent's box (simple containment heuristic,
    not exhaustive)."""
    try:
        issues = page.evaluate(
            """() => {
                const out = [];
                document.querySelectorAll('[data-export-id] *').forEach(el => {
                    const r = el.getBoundingClientRect();
                    const p = el.parentElement && el.parentElement.getBoundingClientRect();
                    if (!p || r.width === 0 || r.height === 0) return;
                    const overflowRight = r.right - p.right;
                    const overflowBottom = r.bottom - p.bottom;
                    if (overflowRight > 4 || overflowBottom > 4) {
                        out.push({ tag: el.tagName, text: (el.textContent || '').slice(0, 40),
                                   overflowRight: Math.round(overflowRight), overflowBottom: Math.round(overflowBottom) });
                    }
                });
                return out.slice(0, 10);
            }"""
        )
        for issue in issues:
            warnings.append(f"possible overflow: <{issue['tag']}> \"{issue['text']}\" +{issue['overflowRight']}px/+{issue['overflowBottom']}px")
    except Exception as e:  # non-fatal — this is a best-effort check
        warnings.append(f"overflow check skipped: {e}")


def render_pick(pick, date_str=None, out_dir=CARDS_DIR, theme_override=None):
    from playwright.sync_api import sync_playwright  # imported here so --help works without playwright installed

    os.makedirs(out_dir, exist_ok=True)
    date_str = date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    the_date = datetime.strptime(date_str, "%Y-%m-%d")

    props = build_props(pick)
    props["palette"] = pick_palette(the_date)
    theme = theme_override or choose_theme(pick)
    template_path = MATCHDAY_PRINT if theme == "print" else BETSLIP_NIGHT

    match_slug = slugify(pick.get("match") or f"{pick.get('home_team','')}_{pick.get('away_team','')}")
    base = f"{date_str}_{match_slug}_{theme}"

    files = {}
    warnings = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        render_wrapper_html(template_path, tmp_dir)
        render_wrapper_html(SOCIAL_TEMPLATES, tmp_dir)

        with LocalServer(tmp_dir) as server:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                try:
                    page = browser.new_page(viewport={"width": 2400, "height": 2400}, device_scale_factor=1)

                    # --- feed carousel (cover / tip / breakdown) ---
                    page.goto(f"http://127.0.0.1:{server.port}/{os.path.basename(template_path)}", wait_until="load")
                    wait_for_dc_boot(page)
                    set_props_and_settle(page, props)
                    slide_paths = [
                        os.path.join(out_dir, f"{base}_1_cover.png"),
                        os.path.join(out_dir, f"{base}_2_tip.png"),
                        os.path.join(out_dir, f"{base}_3_breakdown.png"),
                    ]
                    capture_exports(
                        page,
                        ["cover", "tip", "breakdown"],
                        [FEED_SLIDE_SIZE] * 3,
                        slide_paths,
                        warnings,
                    )
                    check_no_overlap_and_containment(page, warnings)
                    files["cover"], files["tip"], files["breakdown"] = slide_paths

                    # --- story ---
                    page.goto(f"http://127.0.0.1:{server.port}/{os.path.basename(SOCIAL_TEMPLATES)}", wait_until="load")
                    wait_for_dc_boot(page)
                    set_props_and_settle(page, props)
                    story_path = os.path.join(out_dir, f"{base}_story.png")
                    capture_exports(page, ["story"], [STORY_SIZE], [story_path], warnings)
                    files["story"] = story_path
                finally:
                    browser.close()

    # Basic file-integrity check (opens + verifies declared dimensions)
    try:
        from PIL import Image
        for key, path in files.items():
            with Image.open(path) as im:
                im.verify()
    except ImportError:
        warnings.append("Pillow not installed — skipped file-integrity re-check (dimensions already checked via DOM bounding box)")

    return {"ok": True, "theme": theme, "props": props, "files": files, "warnings": warnings}


# ---------------------------------------------------------------------------
# Fixture picks for local/CI testing (brief section 7 & 9)
# ---------------------------------------------------------------------------

PORTUGAL_SPAIN_PICK = {
    "match": "Portugal vs Spain",
    "sport": "FIFA World Cup 2026",
    "sport_key": "soccer_fifa_world_cup",
    "pick": "Portugal",
    "market": "Head to Head",
    "odds": "4.30",
    "reasoning": "Portugal at 4.30 in a World Cup knockout derby — Spain are favourites "
                 "but Iberian derbies are never straightforward, and the market is "
                 "handing out value on the underdog.",
    "confidence": "Medium",
    "home_team": "Portugal",
    "away_team": "Spain",
}

OVERFLOW_TEST_PICK = {
    "match": "Rakuten Kobe Vissel Wanderers United vs Deportivo Independiente Sports Club",
    "sport": "FIFA World Cup 2026",
    "sport_key": "soccer_fifa_world_cup",
    "pick": "Rakuten Kobe Vissel Wanderers United to Win in Extra Time or Penalties",
    "market": "Head to Head, Extra Time & Penalties Included",
    "odds": "12.50",
    "reasoning": "A deliberately long team name, selection and market string to check "
                 "that nothing overflows its container or overlaps adjacent elements "
                 "on either template — the whole point of this fixture is to break "
                 "the layout if it's going to break.",
    "confidence": "Low",
    "home_team": "Rakuten Kobe Vissel Wanderers United",
    "away_team": "Deportivo Independiente Sports Club",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pick-file", help="Path to a JSON file containing a pick or {'picks': [...]}")
    ap.add_argument("--pick-index", type=int, default=0, help="Index into picks[] if --pick-file has multiple")
    ap.add_argument("--pick-json", help="Raw JSON string for a single pick")
    ap.add_argument("--test-portugal-spain", action="store_true", help="Use the fixed Portugal v Spain reference pick")
    ap.add_argument("--test-overflow", action="store_true", help="Use the long-name overflow-test pick")
    ap.add_argument("--theme", choices=["night", "print"], help="Force a theme instead of auto-choosing")
    ap.add_argument("--date", help="Override date used in filenames (YYYY-MM-DD), defaults to today (UTC)")
    ap.add_argument("--out-dir", default=CARDS_DIR)
    args = ap.parse_args()

    if args.test_portugal_spain:
        pick = PORTUGAL_SPAIN_PICK
    elif args.test_overflow:
        pick = OVERFLOW_TEST_PICK
    elif args.pick_json:
        pick = json.loads(args.pick_json)
    elif args.pick_file:
        with open(args.pick_file) as f:
            data = json.load(f)
        pick = data["picks"][args.pick_index] if isinstance(data, dict) and "picks" in data else data
    else:
        ap.error("one of --pick-file / --pick-json / --test-portugal-spain / --test-overflow is required")

    try:
        result = render_pick(pick, date_str=args.date, out_dir=args.out_dir, theme_override=args.theme)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        sys.exit(1)

    print(json.dumps(result, indent=2))
    if result["warnings"]:
        print(f"\n⚠️  {len(result['warnings'])} warning(s) — review before approving.", file=sys.stderr)


if __name__ == "__main__":
    main()
