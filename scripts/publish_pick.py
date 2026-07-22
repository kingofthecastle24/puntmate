#!/usr/bin/env python3
"""
publish_pick.py — the ONLY script that actually posts to Telegram or
Instagram. Runs in the "publish" job, after the "production" environment
approval gate, using the EXACT frozen files from data/review/<pick_id>/
(downloaded as this run's artifact) — never regenerated, never re-read from
whatever's newest on main.

Facebook IS posted to directly as of 2026-07-19 (Micah confirmed the
"linked Instagram" assumption never actually cross-posted anything — Meta
doesn't auto-share API-published IG content to a linked Page). The
2026-07-14 publish_actions failure was a user-token problem, not a dead
API: Page posting works with a PAGE access token holding
pages_manage_posts. See post_facebook.py for token setup. Requires the
FACEBOOK_PAGE_ID secret (and ideally FACEBOOK_PAGE_TOKEN; falls back to
META_PAGE_TOKEN). If the token still lacks permissions, the run logs the
exact fix and Facebook fails independently — nothing else is affected.

Freeze/verify: before publishing anything, this reloads manifest.json and
re-hashes every file it lists. A single mismatch aborts the ENTIRE publish
(nothing goes out on any platform) and requires a fresh approval — see
manifest.py.

Platforms publish independently: if Telegram succeeds and Instagram fails
(or vice versa), the successful post stays live and is reported as such —
one platform's failure never rolls back another's success.

Telegram approval note: per Micah, Telegram is deliberately behind the SAME
single "production" environment gate as Instagram/Facebook for now (phase 1
— prove the whole pipeline out with him as the approver on every platform).
`intended_platforms` is a plain list on post-metadata.json and every platform
here is published from the same single approval; if/when per-platform gating
is wanted later (e.g. Telegram auto-publishes once trusted), that's a matter
of splitting `intended_platforms` handling or adding a second gated job — a
config/workflow change, not a rewrite of this script.

Honors DRY_RUN=true (the default): logs exactly what would be sent to each
platform without calling any API.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from manifest import load_manifest, verify_manifest
from workflow_state import transition, APPROVED, PUBLISHING, PUBLISHED, PARTIALLY_PUBLISHED, PUBLISH_FAILED
import email_service

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
REVIEW_ROOT = os.path.join(REPO_ROOT, "data", "review")
PUBLISHED_DIR = os.path.join(REPO_ROOT, "data", "published")

DRY_RUN = os.environ.get("DRY_RUN", "true").strip().lower() not in ("false", "0", "no")
# RESEND_FAILED (2026-07-23): manual retry mode for the Manual Republish
# workflow. When true and the pick already has a published record, re-attempt
# ONLY the platforms whose prior result wasn't a success (failed, skipped, or
# never attempted) — never re-posts a platform that already went out (e.g.
# Telegram), so a partial-failure retry can't create duplicates.
RESEND_FAILED = os.environ.get("RESEND_FAILED", "").strip().lower() in ("true", "1", "yes")


def already_published(pick_id):
    return os.path.exists(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"))


def _prior_publish_record(pick_id):
    path = os.path.join(PUBLISHED_DIR, f"{pick_id}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _platforms_needing_retry(metadata, prior):
    """Main-post platforms from intended_platforms whose prior result wasn't a
    genuine success (ok:True). 'skipped' (e.g. Facebook before its secret was
    configured) and outright failures both qualify for a retry; a platform
    already ok:True is never touched."""
    retry = []
    for p in metadata.get("intended_platforms", []):
        r = prior.get(p)
        if not (r and r.get("ok") is True):
            retry.append(p)
    return retry


def mark_published(pick_id, results):
    os.makedirs(PUBLISHED_DIR, exist_ok=True)
    with open(os.path.join(PUBLISHED_DIR, f"{pick_id}.json"), "w") as f:
        json.dump(results, f, indent=2)


def publish(review_dir, metadata, telegram_text, instagram_caption, results):
    """Live-publish path. Each platform is independent — one failing must not
    stop or roll back another."""
    platforms = metadata.get("intended_platforms", [])

    # 2026-07-19: a weekend-multi-only post (is_weekend_multi) has no single
    # featured pick at all, so there is no "main" Telegram/Instagram post to
    # send here -- only the per-tier posts further down. Gating this whole
    # block avoids sending a blank/empty main post for that pick_id.
    is_weekend_multi_only = bool(metadata.get("is_weekend_multi"))

    if "telegram" in platforms and not is_weekend_multi_only:
        try:
            from post_telegram import send_picks_card, post_text
            tip_path = os.path.join(review_dir, "tip.png")
            if os.path.exists(tip_path):
                r = send_picks_card(tip_path, caption=telegram_text)
            else:
                r = post_text(telegram_text)
            results["telegram"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
        except Exception as e:
            results["telegram"] = {"ok": False, "error": str(e)}
            print(f"  Telegram error: {e}")

    if "instagram_feed" in platforms and not is_weekend_multi_only:
        try:
            from post_instagram import post_carousel_to_instagram
            ok = post_carousel_to_instagram(
                slide_paths=[os.path.join(review_dir, n) for n in ("cover.png", "tip.png", "breakdown.png") if os.path.exists(os.path.join(review_dir, n))],
                caption=instagram_caption,
                slide_urls=metadata.get("carousel_urls"),
            )
            results["instagram_feed"] = {"ok": bool(ok)}
            if not ok:
                import post_instagram
                results["instagram_feed"]["error"] = post_instagram.LAST_ERROR
        except Exception as e:
            results["instagram_feed"] = {"ok": False, "error": str(e)}
            print(f"  Instagram feed error: {e}")

    if "instagram_story" in platforms and not is_weekend_multi_only:
        try:
            from post_instagram_story import post_story_to_instagram
            media_id = post_story_to_instagram(metadata.get("story_url"))
            results["instagram_story"] = {"ok": media_id is not None, "media_id": media_id}
            if media_id is None:
                import post_instagram_story
                results["instagram_story"]["error"] = getattr(post_instagram_story, "LAST_ERROR", None)
        except Exception as e:
            results["instagram_story"] = {"ok": False, "error": str(e)}
            print(f"  Instagram Story error: {e}")

    import post_facebook
    fb_configured = post_facebook.is_configured()
    if "facebook" in platforms and not fb_configured:
        results["facebook"] = {
            "skipped": True,
            "note": "FACEBOOK_PAGE_ID / page token not configured — add the GitHub secret to enable direct Page posting.",
        }
        print("  Facebook: not configured (FACEBOOK_PAGE_ID missing) — skipped.")

    if "facebook" in platforms and fb_configured and not is_weekend_multi_only:
        try:
            carousel_urls = metadata.get("carousel_urls") or []
            if carousel_urls:
                fb_id = post_facebook.post_photo(carousel_urls[0], instagram_caption or telegram_text)
            else:
                fb_id = post_facebook.post_text(telegram_text)
            results["facebook"] = {"ok": fb_id is not None, "post_id": fb_id}
        except Exception as e:
            results["facebook"] = {"ok": False, "error": str(e)}
            print(f"  Facebook error: {e}")

        # Page Story mirrors the Instagram Story — same image URL.
        if metadata.get("story_url"):
            try:
                story_id = post_facebook.post_story(metadata["story_url"])
                results["facebook_story"] = {"ok": story_id is not None, "story_id": story_id}
            except Exception as e:
                results["facebook_story"] = {"ok": False, "error": str(e)}
                print(f"  Facebook Story error: {e}")

    # Phase 5/6 (2026-07-19): TWO independent multi tiers — Punter Multi and
    # Gambler/Degenerate Multi — each its own secondary Telegram text post
    # AND (new) its own Instagram feed carousel, sent only AFTER the main
    # pick post above, and only if that tier actually cleared the bar that
    # day. Failure in either tier, on either platform, never blocks or rolls
    # back anything else — same independence guarantee as every other
    # platform here. No Instagram Story for multis: the Multi.dc.html
    # template only has a 3-slide feed carousel (cover/legs/breakdown), no
    # story-sized slide, so that's a real, disclosed scope limit, not an
    # oversight.
    for tier in ("punter", "gambler", "degenerate"):
        # BOTH the metadata flag and the frozen file must agree that this
        # tier fired THIS run — file existence alone allowed a stale multi
        # from an earlier same-pick_id run to be re-published (caught in
        # dry run #56, 2026-07-19; build_review_package also now deletes
        # stale tier files, this is the second line of defence).
        if not metadata.get(f"has_{tier}_multi"):
            continue
        text_path = os.path.join(review_dir, f"{tier}-multi-post.txt")
        if not os.path.exists(text_path):
            continue  # that tier didn't clear the bar today — nothing to post

        with open(text_path) as f:
            tier_text = f.read()

        if "telegram" in platforms:
            try:
                from post_telegram import post_text
                r = post_text(tier_text)
                results[f"telegram_{tier}_multi"] = {"ok": bool(r and r.get("ok", True)), "detail": r}
            except Exception as e:
                results[f"telegram_{tier}_multi"] = {"ok": False, "error": str(e)}
                print(f"  Telegram {tier} multi error: {e}")

        if "instagram_feed" in platforms:
            multi_slide_paths = [
                os.path.join(review_dir, f"{tier}_multi_{n}.png")
                for n in ("cover", "legs", "breakdown")
                if os.path.exists(os.path.join(review_dir, f"{tier}_multi_{n}.png"))
            ]
            if not multi_slide_paths:
                # Graphic render failed or was skipped that run (see
                # main.py's render_multi_cards) — the Telegram text above
                # still went out; there just isn't a card to post here.
                continue
            try:
                from post_instagram import post_carousel_to_instagram
                ok = post_carousel_to_instagram(
                    slide_paths=multi_slide_paths,
                    caption=tier_text,
                    slide_urls=metadata.get(f"{tier}_multi_carousel_urls"),
                )
                results[f"instagram_{tier}_multi"] = {"ok": bool(ok)}
            except Exception as e:
                results[f"instagram_{tier}_multi"] = {"ok": False, "error": str(e)}
                print(f"  Instagram {tier} multi error: {e}")

        if "facebook" in platforms and fb_configured:
            tier_urls = metadata.get(f"{tier}_multi_carousel_urls") or []
            try:
                if tier_urls:
                    fb_id = post_facebook.post_photo(tier_urls[0], tier_text)
                else:
                    fb_id = post_facebook.post_text(tier_text)
                results[f"facebook_{tier}_multi"] = {"ok": fb_id is not None, "post_id": fb_id}
            except Exception as e:
                results[f"facebook_{tier}_multi"] = {"ok": False, "error": str(e)}
                print(f"  Facebook {tier} multi error: {e}")

    return results


def dry_run_report(metadata, telegram_text, instagram_caption, review_dir=None):
    print("=" * 55)
    print("DRY RUN — no platform will receive a post")
    print("=" * 55)
    is_weekend_multi_only = bool(metadata.get("is_weekend_multi"))
    if is_weekend_multi_only:
        print("\n(weekend-multi-only post — no single featured pick, see tier reports below)")
    for platform in metadata.get("intended_platforms", []):
        if is_weekend_multi_only:
            break  # nothing "main" to report -- only the per-tier section below applies
        print(f"\n[{platform}]")
        if platform == "telegram":
            print(f"  Caption:\n{telegram_text[:400]}")
        elif platform == "instagram_feed":
            print(f"  Would post carousel: {metadata.get('carousel_urls')}")
            print(f"  Caption:\n{instagram_caption[:400]}")
        elif platform == "instagram_story":
            print(f"  Would post Story: {metadata.get('story_url')}")
        elif platform == "facebook":
            print(f"  Would post photo to FB Page: {(metadata.get('carousel_urls') or ['(text-only fallback)'])[0]}")
            if metadata.get("story_url"):
                print(f"  Would post FB Page Story: {metadata.get('story_url')}")

    if review_dir:
        for tier in ("punter", "gambler", "degenerate"):
            if not metadata.get(f"has_{tier}_multi"):
                continue  # same stale-file guard as the live publish loop
            text_path = os.path.join(review_dir, f"{tier}-multi-post.txt")
            if not os.path.exists(text_path):
                continue
            with open(text_path) as f:
                tier_text = f.read()
            print(f"\n[{tier}_multi — telegram]")
            print(f"  Caption:\n{tier_text[:400]}")
            carousel_urls = metadata.get(f"{tier}_multi_carousel_urls")
            has_graphic = any(
                os.path.exists(os.path.join(review_dir, f"{tier}_multi_{n}.png"))
                for n in ("cover", "legs", "breakdown")
            )
            print(f"\n[{tier}_multi — instagram_feed]")
            if has_graphic:
                print(f"  Would post carousel: {carousel_urls}")
            else:
                print("  No graphic rendered this run — would skip Instagram, Telegram text only.")

    print("\n" + "=" * 55)
    print("DRY RUN complete — nothing was actually sent.")
    print("=" * 55)


def main():
    review_dir = os.environ.get("REVIEW_DIR")
    if not review_dir:
        pick_id = os.environ.get("PICK_ID", "")
        review_dir = os.path.join(REVIEW_ROOT, pick_id)

    meta_path = os.path.join(review_dir, "post-metadata.json")
    if not os.path.exists(meta_path):
        print("No post-metadata.json found — nothing to publish.")
        return

    with open(meta_path) as f:
        metadata = json.load(f)

    # 2026-07-19: a weekend multi post (is_weekend_multi) has has_pick=False
    # (there's no single featured selection) but IS something to publish if
    # either tier cleared the bar -- has_pick alone is no longer sufficient
    # to decide "nothing to publish".
    has_something_to_publish = (metadata.get("has_pick") or metadata.get("has_punter_multi")
                                or metadata.get("has_gambler_multi") or metadata.get("has_degenerate_multi"))
    if not has_something_to_publish:
        print("NO_BET — nothing to publish.")
        return

    pick_id = metadata["pick_id"]

    if already_published(pick_id) and not RESEND_FAILED:
        print(f"::notice::{pick_id} was already published — skipping to avoid a duplicate post.")
        return

    # A weekend-multi-only post has no main telegram-post.txt/instagram-
    # caption.txt (no single featured pick) -- these are read conditionally
    # so main() doesn't crash, and publish() below never sends a blank
    # "main pick" post for this pick_id (gated on is_weekend_multi).
    telegram_path = os.path.join(review_dir, "telegram-post.txt")
    instagram_path = os.path.join(review_dir, "instagram-caption.txt")
    telegram_text = open(telegram_path).read() if os.path.exists(telegram_path) else ""
    instagram_caption = open(instagram_path).read() if os.path.exists(instagram_path) else ""

    if DRY_RUN:
        # Dry runs (manual testing) don't move workflow state at all — only a
        # real approved run does.
        manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
        verify_manifest(manifest, review_dir)  # surfaced in the report either way
        if RESEND_FAILED and already_published(pick_id):
            # In resend mode the dry run must reflect the RESEND plan, not the
            # generic all-platforms report — otherwise it misleadingly shows
            # "[telegram] would post" for a platform that already went out.
            prior = _prior_publish_record(pick_id)
            retry_platforms = _platforms_needing_retry(metadata, prior)
            print("=" * 55)
            print("DRY RUN (RESEND) — no platform will receive a post")
            print("=" * 55)
            print(f"pick_id: {pick_id}")
            print(f"Prior results: " + ", ".join(f"{k}={'ok' if v.get('ok') else v.get('skipped') and 'skipped' or 'FAILED'}" for k, v in prior.items()))
            if retry_platforms:
                print(f"Would RETRY only: {retry_platforms}")
                print("(platforms already ok are left untouched — no duplicate posts)")
            else:
                print("Nothing to retry — every intended platform already succeeded.")
            return
        dry_run_report(metadata, telegram_text, instagram_caption, review_dir)
        return

    # This script only ever runs after the GitHub environment approval gate
    # passed, so AWAITING_APPROVAL -> APPROVED is safe here. Checksum
    # verification happens INSIDE the PUBLISHING state — a mismatch is a
    # publish-time failure (PUBLISHING -> PUBLISH_FAILED), not a rejection.
    # ── Manual resend of only the platforms that didn't succeed ──────────
    if RESEND_FAILED and already_published(pick_id):
        prior = _prior_publish_record(pick_id)
        retry_platforms = _platforms_needing_retry(metadata, prior)
        if not retry_platforms:
            print(f"Nothing to retry for {pick_id} — every intended platform already succeeded.")
            return
        print(f"RESEND — pick_id={pick_id}, retrying only: {retry_platforms} (prior successes untouched)")

        # verify the frozen files still match before re-sending anything
        manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
        okm, mismatches = verify_manifest(manifest, review_dir)
        if not okm:
            print("::error::Checksum mismatch — refusing to resend.")
            for m in mismatches:
                print(f"  - {m}")
            sys.exit(1)

        retry_meta = {**metadata, "intended_platforms": retry_platforms}
        new_results = {}
        publish(review_dir, retry_meta, telegram_text, instagram_caption, new_results)

        merged = {**prior, **new_results}  # new attempts override; prior successes kept
        print("\n" + "=" * 55)
        for platform, r in merged.items():
            status = "OK" if (r.get("ok") is True or r.get("skipped") is True) else "FAILED"
            print(f"[{status}] {platform}: {r}")
        print("=" * 55)
        mark_published(pick_id, merged)

        real = [p for p in merged if not merged[p].get("skipped")]
        all_ok = all(merged[p].get("ok") for p in real) if real else False
        any_ok = any(merged[p].get("ok") for p in real) if real else False
        new_state = PUBLISHED if all_ok else (PARTIALLY_PUBLISHED if any_ok else PUBLISH_FAILED)
        try:
            transition(REPO_ROOT, pick_id, new_state,
                       note=f"manual resend of {retry_platforms}: " + json.dumps({k: v.get("ok", v.get("skipped")) for k, v in new_results.items()}))
        except Exception as e:
            print(f"::warning::state not advanced ({e}); publish record still updated.")
        metadata["_telegram_text"] = telegram_text
        metadata["_instagram_caption"] = instagram_caption
        email_service.send_result_email(metadata, merged, new_state)
        if new_state != PUBLISHED:
            print(f"::warning::Resend ended in state {new_state} — see results above.")
        return

    auto_mode = os.environ.get("AUTO_PUBLISH", "").strip().lower() == "true"
    approval_note = (
        "AUTO-PUBLISH TRIAL — no human gate; copy validator (hard-fail at freeze) was the only gate"
        if auto_mode else "approval confirmed, entering publish"
    )
    transition(REPO_ROOT, pick_id, APPROVED, note=approval_note)
    transition(REPO_ROOT, pick_id, PUBLISHING)

    # ── Freeze verification — the whole point of the manifest system ──────
    manifest = load_manifest(os.path.join(review_dir, "manifest.json"))
    ok, mismatches = verify_manifest(manifest, review_dir)
    if not ok:
        print("::error::Checksum mismatch — one or more frozen files changed since approval. REFUSING to publish.")
        for m in mismatches:
            print(f"  - {m}")
        transition(REPO_ROOT, pick_id, PUBLISH_FAILED, note="checksum mismatch, publish blocked")
        email_service.send_result_email(metadata, {"error": "checksum mismatch — publish blocked, see run logs"}, "PUBLISH_FAILED")
        sys.exit(1)

    print(f"LIVE PUBLISH — pick_id={pick_id}, platforms={metadata.get('intended_platforms')}")
    results = {}
    publish(review_dir, metadata, telegram_text, instagram_caption, results)

    def _platform_ok(r):
        return r.get("ok") is True or r.get("skipped") is True

    # Facebook counts as a real platform now (2026-07-19) — the only results
    # excluded from the success calculation are explicitly skipped ones
    # (e.g. Facebook before its secret is configured).
    real_platforms = [p for p in results if not results[p].get("skipped")]
    all_ok = all(results[p].get("ok") for p in real_platforms) if real_platforms else False
    any_ok = any(results[p].get("ok") for p in real_platforms) if real_platforms else False

    print("\n" + "=" * 55)
    for platform, r in results.items():
        status = "OK" if _platform_ok(r) else "FAILED"
        print(f"[{status}] {platform}: {r}")
    print("=" * 55)

    mark_published(pick_id, results)

    if all_ok:
        final_state = PUBLISHED
    elif any_ok:
        final_state = PARTIALLY_PUBLISHED
    else:
        final_state = PUBLISH_FAILED
    transition(REPO_ROOT, pick_id, final_state, note=json.dumps({k: v.get("ok", v.get("status")) for k, v in results.items()}))

    metadata["_telegram_text"] = telegram_text
    metadata["_instagram_caption"] = instagram_caption
    email_service.send_result_email(metadata, results, final_state)

    if final_state != PUBLISHED:
        print(f"::warning::Publish ended in state {final_state} — see results above.")


if __name__ == "__main__":
    main()
