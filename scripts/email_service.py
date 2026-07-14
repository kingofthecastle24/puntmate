#!/usr/bin/env python3
"""
email_service.py — Gmail-based preview + result email notifications.

No email system existed anywhere in this repo before (confirmed by grepping
for smtp/gmail/email across scripts/ and every .md/.env file) — this is a new,
minimal implementation using Python's stdlib smtplib over Gmail's SMTP, not a
second overlapping system.

Required env vars / GitHub Secrets (documented in .env.example and README):
  GMAIL_SENDER_EMAIL   — the Gmail address PuntMate sends FROM (a Gmail App
                          Password is required, not the normal account password)
  GMAIL_APP_PASSWORD    — the 16-character Gmail App Password for that account
  PUNTMATE_REPORT_EMAIL — where preview/result emails are sent TO (Micah's address)

If any of these are unset, every function here degrades to printing a clear
::warning:: to the GitHub Actions log and returning False — it never raises
and never blocks the pipeline, because a missing email config must not be
able to silently block or silently force an approval (see the "Gmail preview
failure must not allow blind approval unless Dispatch/GitHub has an equally
complete visual preview" requirement — preview.html + the job summary are
that equally-complete fallback).

No secret value is ever printed, logged, or included in any email body.
"""
import base64
import mimetypes
import os
import smtplib
from email.message import EmailMessage

SENDER = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
RECIPIENT = os.environ.get("PUNTMATE_REPORT_EMAIL", "").strip()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _configured():
    return bool(SENDER and APP_PASSWORD and RECIPIENT)


def _send(subject, html_body, image_paths=None):
    if not _configured():
        missing = [n for n, v in (("GMAIL_SENDER_EMAIL", SENDER), ("GMAIL_APP_PASSWORD", APP_PASSWORD), ("PUNTMATE_REPORT_EMAIL", RECIPIENT)) if not v]
        print(f"::warning::Email not sent — missing env var(s): {', '.join(missing)}. "
              f"Subject would have been: {subject!r}. Falling back to the GitHub Actions "
              f"job summary / Dispatch preview as the review surface for this run.")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = RECIPIENT
    msg.set_content("This email requires an HTML-capable client to view the preview.")

    cids = []
    for i, path in enumerate(image_paths or []):
        if not os.path.exists(path):
            continue
        cid = f"image{i}"
        cids.append((cid, path))
    if cids:
        html_with_images = html_body + "".join(f'<p><img src="cid:{cid}" style="max-width:420px"/></p>' for cid, _ in cids)
    else:
        html_with_images = html_body
    msg.add_alternative(html_with_images, subtype="html")

    for cid, path in cids:
        ctype, _ = mimetypes.guess_type(path)
        maintype, subtype = (ctype or "image/png").split("/", 1)
        with open(path, "rb") as f:
            msg.get_payload()[-1].add_related(f.read(), maintype=maintype, subtype=subtype, cid=f"<{cid}>")

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.login(SENDER, APP_PASSWORD)
            server.send_message(msg)
        print(f"Email sent to {RECIPIENT}: {subject}")
        return True
    except Exception as e:
        # Never expose the app password in an error string; smtplib exceptions
        # don't include it, but keep this defensive regardless.
        print(f"::warning::Failed to send email ({subject!r}): {e}")
        return False


def _metadata_table(metadata, exclude=()):
    rows = "".join(
        f"<tr><td style='padding:4px 10px;color:#666'>{k}</td><td style='padding:4px 10px'>{v}</td></tr>"
        for k, v in metadata.items() if k not in exclude and not isinstance(v, (list, dict))
    )
    return f"<table>{rows}</table>"


def send_preview_email(metadata, image_paths, telegram_text, instagram_caption, approval_url):
    """Sent before the approval gate. Subject format:
    'PuntMate Post Approval Required — [Fixture or No Bet] — [Date]'
    """
    fixture = metadata.get("match", "No Bet")
    subject = f"PuntMate Post Approval Required — {fixture} — {metadata.get('post_date', '')}"

    warnings = metadata.get("research_warnings", [])
    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{w}</li>" for w in warnings)
        warnings_html = f"<h3>Internal research warning</h3><ul>{items}</ul>"

    body = f"""
    <h2>PuntMate — Approval Required</h2>
    <p><a href="{approval_url}">Open the GitHub Actions approval step →</a></p>
    <h3>Telegram (final text)</h3>
    <pre style="white-space:pre-wrap;background:#f5f5f5;padding:10px">{telegram_text}</pre>
    <h3>Instagram caption (final text)</h3>
    <pre style="white-space:pre-wrap;background:#f5f5f5;padding:10px">{instagram_caption}</pre>
    <h3>Metadata</h3>
    {_metadata_table(metadata)}
    {warnings_html}
    <p>Run ID: {metadata.get('run_id','')} · pick_id: {metadata.get('pick_id','')}</p>
    """
    return _send(subject, body, image_paths)


def send_no_bet_email(metadata):
    subject = f"PuntMate Post Approval Required — No Bet — {metadata.get('post_date', '')}"
    body = f"""
    <h2>PuntMate — No Bet Today</h2>
    <p>{metadata.get('reasoning', '')}</p>
    <p>Nothing to approve — no post was generated, nothing will be published.</p>
    {_metadata_table(metadata, exclude=("reasoning",))}
    """
    return _send(subject, body, [])


def send_result_email(metadata, results, state):
    fixture = metadata.get("match", "No Bet")
    subject = f"PuntMate Post {state.title()} — {fixture} — {metadata.get('post_date', '')}"
    rows = "".join(
        f"<tr><td style='padding:4px 10px'>{platform}</td><td style='padding:4px 10px'>{r}</td></tr>"
        for platform, r in results.items()
    )
    body = f"""
    <h2>PuntMate — Publish Result: {state}</h2>
    <table>{rows}</table>
    <h3>Final Telegram text</h3><pre style="white-space:pre-wrap;background:#f5f5f5;padding:10px">{metadata.get('_telegram_text','')}</pre>
    <h3>Final Instagram caption</h3><pre style="white-space:pre-wrap;background:#f5f5f5;padding:10px">{metadata.get('_instagram_caption','')}</pre>
    <p>Run ID: {metadata.get('run_id','')} · pick_id: {metadata.get('pick_id','')}</p>
    """
    return _send(subject, body, [])


def send_rejection_email(metadata):
    fixture = metadata.get("match", "No Bet")
    subject = f"PuntMate Post Rejected — {fixture} — {metadata.get('post_date', '')}"
    body = f"""
    <h2>PuntMate — Post Rejected</h2>
    <p>This post was rejected in the GitHub Actions approval step. Nothing was published to any platform.</p>
    {_metadata_table(metadata)}
    """
    return _send(subject, body, [])
