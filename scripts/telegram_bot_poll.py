"""
telegram_bot_poll.py -- lets Micah settle a weekend multi by messaging the
PuntMate bot directly, instead of running set_multi_result.py by hand.

Runs on a short GitHub Actions schedule (owner_chat.yml) and does a single
Telegram getUpdates poll. On purpose it can do exactly ONE thing: write a
win/loss/void result for an already-published weekend multi to
data/multi_results.json via set_multi_result.set_result -- the same function
and file set_multi_result.py's CLI uses. It never imports any of the public-
platform posting modules, and only ever reads secrets TELEGRAM_BOT_TOKEN and
OWNER_CHAT_ID (never a Meta secret), so it has no way to post publicly, by
design, not just by convention.

Security: only messages from OWNER_CHAT_ID are ever acted on. Anyone else who
DMs the bot (it's the same bot that posts to the public channel, so its
username is public) gets silently ignored -- their update is still marked
read (offset advanced) so it doesn't requeue forever, but nothing is ever
written or replied for a non-owner chat.

Command grammar (case-insensitive):
    /settle <tier> <win|loss|void>
    /settle <YYYY-MM-DD> <tier> <win|loss|void>
tier is punter, gambler or degenerate. The short form only works when exactly
one published, un-settled multi exists for that tier -- with more than one
candidate it lists them and asks for the dated form instead of guessing.
"""

import json
import os
import re

import requests

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
PUBLISHED_DIR = os.path.join(REPO_ROOT, "data", "published")
MULTI_RESULTS_PATH = os.path.join(REPO_ROOT, "data", "multi_results.json")
OFFSET_PATH = os.path.join(REPO_ROOT, "data", "state", "telegram_bot_offset.json")

TIERS = ("punter", "gambler", "degenerate")
RESULTS = ("win", "loss", "void")

SETTLE_RE = re.compile(
    r"^/settle\s+(?:(\d{4}-\d{2}-\d{2})\s+)?(punter|gambler|degenerate)\s+(win|loss|void)\s*$",
    re.IGNORECASE,
)


def _read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load_offset():
    return _read_json(OFFSET_PATH, {}).get("offset", 0)


def save_offset(offset):
    os.makedirs(os.path.dirname(OFFSET_PATH), exist_ok=True)
    with open(OFFSET_PATH, "w") as f:
        json.dump({"offset": offset}, f, indent=2)
        f.write("\n")


def already_settled(pick_id, tier):
    return tier in (_read_json(MULTI_RESULTS_PATH, {}).get(pick_id) or {})


def unsettled_multis_for_tier(tier):
    """[(pick_id, date_str), ...] for every published weekend multi where this
    tier's public Telegram post succeeded and no result is recorded yet.
    Sorted oldest first (clear the backlog in order)."""
    out = []
    if not os.path.isdir(PUBLISHED_DIR):
        return out
    for name in sorted(os.listdir(PUBLISHED_DIR)):
        if not name.endswith("_weekend_multi.json"):
            continue
        pick_id = name[:-5]
        pub = _read_json(os.path.join(PUBLISHED_DIR, name), {})
        if (pub.get(f"telegram_{tier}_multi") or {}).get("ok") is not True:
            continue
        if already_settled(pick_id, tier):
            continue
        date_str = pick_id.split("_weekend_multi")[0]
        out.append((pick_id, date_str))
    return out


def find_target(date_str, tier):
    """Returns (pick_id, error_message). Exactly one of the two is set."""
    candidates = unsettled_multis_for_tier(tier)
    if date_str:
        pick_id = f"{date_str}_weekend_multi"
        if not any(pid == pick_id for pid, _ in candidates):
            return None, (
                f"No unsettled, published {tier} multi found for {date_str}. "
                f"Unsettled {tier} multis: "
                + (", ".join(d for _, d in candidates) or "(none)")
            )
        return pick_id, None
    if not candidates:
        return None, f"Nothing unsettled for the {tier} multi right now."
    if len(candidates) > 1:
        dates = ", ".join(d for _, d in candidates)
        return None, (
            f"More than one unsettled {tier} multi ({dates}) -- "
            f"use /settle <date> {tier} <result> to pick one."
        )
    return candidates[0][0], None


def apply_settle(date_str, tier, result):
    """Returns a reply string. Writes to multi_results.json on success."""
    import set_multi_result

    pick_id, err = find_target(date_str, tier)
    if err:
        return err
    set_multi_result.set_result(pick_id, tier, result, path=set_multi_result.PATH)
    return f"Recorded: {pick_id} — {tier} multi = {result}."


def handle_text(text):
    """Returns a reply string, or None if the text isn't a recognised command
    (so the bot stays silent rather than replying to every random message)."""
    text = (text or "").strip()
    if text.lower() in ("/help", "/start"):
        return (
            "Settle a weekend multi:\n"
            "/settle <tier> <win|loss|void>\n"
            "/settle <YYYY-MM-DD> <tier> <win|loss|void>\n"
            "tier = punter, gambler or degenerate."
        )
    m = SETTLE_RE.match(text)
    if not m:
        return None
    date_str, tier, result = m.group(1), m.group(2).lower(), m.group(3).lower()
    return apply_settle(date_str, tier, result)


def send_reply(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception as e:  # noqa: BLE001 -- never crash the poll over a reply
        print(f"  reply send failed: {e}")


def poll_once():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    owner_chat_id = os.environ.get("OWNER_CHAT_ID", "")
    if not token or not owner_chat_id:
        print("TELEGRAM_BOT_TOKEN / OWNER_CHAT_ID not set -- nothing to do.")
        return
    owner_chat_id = int(owner_chat_id)

    offset = load_offset()
    r = requests.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": offset + 1, "timeout": 0},
        timeout=15,
    )
    r.raise_for_status()
    updates = r.json().get("result", [])

    highest_seen = offset
    for upd in updates:
        highest_seen = max(highest_seen, upd["update_id"])
        msg = upd.get("message") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") != owner_chat_id:
            continue  # not Micah -- ignore, but offset still advances below
        reply = handle_text(msg.get("text"))
        if reply:
            print(f"  -> {reply}")
            send_reply(token, owner_chat_id, reply)

    if highest_seen != offset:
        save_offset(highest_seen)


if __name__ == "__main__":
    poll_once()
