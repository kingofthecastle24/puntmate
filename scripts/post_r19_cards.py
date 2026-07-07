#!/usr/bin/env python3
"""PuntMate R19 — generate banker card + post banker image & multi text to Telegram/Facebook"""
import sys, os
sys.path.insert(0, 'scripts')

from generate_picks_image import generate_carousel
import requests

OUT = 'data/cards'
os.makedirs(OUT, exist_ok=True)

FOOTER = "R18 · Gamble responsibly · 0800 654 655 · gamblinghelpline.co.nz"
TG_BOT  = os.environ['TG_BOT']
TG_CHAN  = os.environ['TG_CHAN']
FB_TOKEN = os.environ.get('FB_TOKEN', '')
FB_PAGE  = os.environ.get('FB_PAGE', '')
NL = "\n"

single = {
    'match': 'Storm vs Titans', 'home_team': 'Melbourne Storm',
    'away_team': 'Gold Coast Titans', 'selection': 'Storm to Win',
    'odds': '1.40', 'market': 'Head to Head', 'sport_label': 'NRL 2026',
    'sport_tag': 'NRL', 'cover_theme': 'Banker of the Day',
    'analysis': 'Storm are the benchmark at AAMI Park. Titans winless away in seven straight. Back the class side.',
    'confidence': 4, 'riskTagline': 'LOW RISK · BANKER PLAY · BACK THE STORM', 'big_game': False,
}

print('Generating banker card...')
spaths = generate_carousel(single, OUT)
print('Banker:', spaths[0])


def tg_photo(path, caption):
    with open(path, 'rb') as f:
        r = requests.post(
            'https://api.telegram.org/bot' + TG_BOT + '/sendPhoto',
            data={'chat_id': TG_CHAN, 'caption': caption, 'parse_mode': 'Markdown'},
            files={'photo': f}, timeout=30)
    j = r.json()
    print('TG photo', os.path.basename(path), 'ok:', j.get('ok'), j.get('description', ''))
    return j


def tg_text(text):
    r = requests.post(
        'https://api.telegram.org/bot' + TG_BOT + '/sendMessage',
        json={'chat_id': TG_CHAN, 'text': text, 'parse_mode': 'Markdown'},
        timeout=30)
    j = r.json()
    print('TG text ok:', j.get('ok'), j.get('description', ''))
    return j


def fb_photo(path, caption):
    if not FB_TOKEN or not FB_PAGE:
        print('FB skipped (no token)'); return
    with open(path, 'rb') as f:
        ir = requests.post('https://api.imgur.com/3/image',
            headers={'Authorization': 'Client-ID 546c25a59c58ad7'},
            files={'image': f}, timeout=30)
    ij = ir.json()
    if not ij.get('success'):
        print('Imgur failed:', ij.get('data', {})); return
    img_url = ij['data']['link']
    print('Imgur:', img_url)
    r = requests.post(
        'https://graph.facebook.com/v19.0/' + FB_PAGE + '/photos',
        data={'url': img_url, 'caption': caption, 'access_token': FB_TOKEN}, timeout=30)
    j = r.json()
    print('FB', j.get('id'), j.get('error', ''))


def fb_text(text):
    if not FB_TOKEN or not FB_PAGE:
        print('FB text skipped (no token)'); return
    r = requests.post(
        'https://graph.facebook.com/v19.0/' + FB_PAGE + '/feed',
        data={'message': text, 'access_token': FB_TOKEN}, timeout=30)
    j = r.json()
    print('FB feed', j.get('id') or j.get('post_id'), j.get('error', ''))


banker_caption = (
    "\U0001f3af *STORM TO WIN @ 1.40 | NRL R19*" + NL +
    "Banker play. Class side at home." + NL +
    "_" + FOOTER + "_"
)
multi_caption = (
    "\U0001f525 *HOME TREBLE | NRL R19*" + NL +
    "Storm 1.40 + Warriors 1.40 + Dolphins 1.52 = *$2.98*" + NL +
    "_" + FOOTER + "_"
)
fb_banker = banker_caption.replace('*', '').replace('_', '')
fb_multi  = multi_caption.replace('*', '').replace('_', '')

print('\nPosting banker to Telegram...')
tg_photo(spaths[0], banker_caption)

print('\nPosting multi to Telegram (text)...')
tg_text(multi_caption)

print('\nPosting banker to Facebook...')
fb_photo(spaths[0], fb_banker)

print('\nPosting multi to Facebook (text)...')
fb_text(fb_multi)

print('\nDone!')
