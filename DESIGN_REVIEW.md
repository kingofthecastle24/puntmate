# Mandatory PuntMate design review

Every graphic and public destination needs final rendered-pixel review before
publishing: picks, multis, results, recaps, news and reshares. Compare CURRENT
approved reference pixels, not template names. Check heavy logo, hierarchy,
spacing, clipping, wording, facts, and Story header/footer safe areas. Render
success, readability, an old renderer pin and a previous post are not a pass.
Failure or missing evidence means HOLD. Never generate a PASS automatically.

Live-capable workflow steps now have a fail-closed receipt check. No pass
receipts are seeded. Thus routine auto-publish, manual retries and legacy
routes cannot send on main without a fresh review record. The receipt binds
the exact GitHub run/job, all final data bytes, actual outgoing asset hashes,
destinations, visual reference and every checklist item. Prepare/render-only
steps stay usable; a combined render/send step must first use a separate
preparation path, never bypass the gate. Publish from a reviewed frozen
package. Record invalidation after changed data is deliberately conservative.

A receipt is audit evidence of a review, NOT permission from the owner. Keep
all existing factual, authority, duplicate and destination checks. Scripts
run outside these workflows also require the same review before calling a
sender. Browser reshares require an on-screen visual and wording check.

Colorado replacement still requires Micah's approval. Results and recaps stay
paused in config/public_delivery.json. No cadence change is authorized by
this rule. No existing receipts should be deleted to evade duplicate checks.

Review record: data/design_reviews/<run_id>-<job>.json, with run_id, job,
snapshot_sha256 (scripts/design_review_gate.py --snapshot), decision PASS,
reviewer, reviewed_at, style_reference, destinations, outgoing_assets
(path-to-SHA256 mapping), and checks (all names in CHECKS true). An actual
review must precede the record. Do not copy old review records.

Results default: one daily roundup only when new verified outcomes, with day outcomes plus week-to-date W/L and strike rate by lane; whole multis separate. Sunday full recap replaces daily content. Telegram plus Instagram Stories only, never feed/Facebook. First roundup composition requires owner proof review. The old per-result sender remains disabled until replaced.

Mandatory copy review includes every caption, Telegram text, baked-in breakdown, claims and CTA. The per-run receipt must include captions_and_all_public_copy=true after reviewing the exact final words and their sources. Current frozen packages from before a validator fix do not inherit permission: publish_pick.py reruns validate_post on the exact loaded captions at send/retry time. Source edits do not repair already-live captions or frozen historic packages.

## Owner copy instructions, 7 November 2026
Carousel covers use "Swipe right", never "below". Check direction for each destination; standalone Stories do not get carousel swipe copy.
Results explain how the match played out, especially close losses. Keep the result prominent and counted. Use source-backed score/OT/match context, no invented unlucky/dominance claims or excuses. Record exact context source and check time; no bare LOSS-only live updates. Approved outcome+record layout does not authorize retrospective reposts or erase history.
