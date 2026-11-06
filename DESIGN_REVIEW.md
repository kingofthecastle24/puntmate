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
