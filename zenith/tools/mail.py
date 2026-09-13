"""Mail adapter — Gmail IMAP read + Resend (API) send.

Zenith's inbox is the `agm.quest` catch-all: Cloudflare Email Routing forwards
every address to the user's Gmail, and Zenith reads Gmail over IMAP. Sending uses
Resend (Resend API key) so messages go out as `Zenith <zenith@agm.quest>`,
which Cloudflare/Resend verify with SPF/DKIM/DMARC.

Everything degrades gracefully: missing config → a clear message, not a crash.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import httpx

from ..core.config import settings

_IMAP_PORT = 993
_RESEND_URL = "https://api.resend.com/emails"


# ── capability flags ────────────────────────────────────────────────────────

def _imap_ok() -> bool:
    # Gmail app password OR legacy IMAP creds.
    return bool(settings.gmail_user and (settings.gmail_app_password or settings.mail_imap_pass))


def _resend_ok() -> bool:
    return bool(settings.resend_api_key)


# ── Gmail IMAP read ─────────────────────────────────────────────────────────

def _imap_creds():
    """Return (host, user, password). Prefers the Gmail path."""
    user = settings.gmail_user or settings.mail_imap_user
    password = settings.gmail_app_password or settings.mail_imap_pass
    return settings.mail_imap_host or "imap.gmail.com", user, password


def _fmt_email_date(raw: str | None) -> str:
    """Parse an email RFC2822 Date header into a local-time ISO string.

    Returns '<no date>' when the header is malformed, so Zenith can still say
    something rather than silently guessing.
    """
    if not raw:
        return "<no date>"
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return "<no date>"
    # Normalize to the container's local zone (TZ=Asia/Kolkata by default) so
    # the model sees a human-friendly time, not UTC offsets.
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(os.getenv("TZ", "Asia/Kolkata"))
        dt = dt.astimezone(tz)
    except Exception:
        tz = None
    return dt.strftime("%Y-%m-%d %H:%M")


async def search(query: str = "", n: int = 5) -> str:
    """Search the inbox. Returns uid · Date · From · Subject per line.

    The date matters — Zenith needs to know WHEN an email arrived, not just
    that it exists, or "any new mail?" has no answer.
    """
    if not _imap_ok():
        return ("Email isn't connected yet — set GMAIL_USER + GMAIL_APP_PASSWORD "
                "in .env (the app password for 2-Step verification).")
    host, user, password = _imap_creds()
    try:
        import imaplib
    except ImportError:
        return "[mail] imaplib unavailable."
    try:
        M = imaplib.IMAP4_SSL(host, _IMAP_PORT, timeout=15)
        M.login(user, password)
        M.select("INBOX")
        if query:
            typ, data = M.search(None, "TEXT", f'"{query}"')
        else:
            typ, data = M.search(None, "ALL")
        ids = (data[0] or b"").split() if data else []
        if not ids:
            M.logout()
            return "Inbox empty."
        ids = ids[-min(n, 20):]
        import email as email_mod
        lines = []
        for uid in ids:
            typ, msg = M.fetch(uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if typ != "OK" or not msg or not (msg[0] or b""):
                continue
            header = (msg[0][1] or b"").decode(errors="replace")
            msg_obj = email_mod.message_from_string(header)
            frm = (msg_obj.get("From") or "(no from)").strip()
            thdr = (msg_obj.get("Subject") or "(no subject)").strip()
            d = _fmt_email_date(msg_obj.get("Date"))
            lines.append(f"{uid.decode()} · {d} · {frm} · {thdr}")
        M.logout()
        return "\n".join(lines) or "No messages found."
    except Exception as exc:
        return f"[mail] {exc}"


async def read(uid: str) -> str:
    """Fetch one message and return Date/From/Subject/plain-text body.

    The Date is essential context — the model must not present an old email as
    fresh, or guess a time that isn't there.
    """
    if not _imap_ok():
        return "Email isn't connected yet."
    host, user, password = _imap_creds()
    try:
        import imaplib
    except ImportError:
        return "[mail] imaplib unavailable."
    try:
        M = imaplib.IMAP4_SSL(host, _IMAP_PORT, timeout=15)
        M.login(user, password)
        M.select("INBOX")
        typ, msg = M.fetch(str(uid), "(RFC822)")
        if typ != "OK" or not msg or not msg[0]:
            M.logout()
            return f"Message {uid} not found."
        import email as email_mod

        msg_obj = email_mod.message_from_bytes(msg[0][1])
        M.logout()
        body = ""
        if msg_obj.is_multipart():
            for part in msg_obj.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(errors="replace") or ""
                    break
        else:
            body = msg_obj.get_payload(decode=True).decode(errors="replace") or ""
        d = _fmt_email_date(msg_obj.get("Date"))
        return (f"Date: {d}\nFrom: {msg_obj.get('From')}\nSubject: {msg_obj.get('Subject')}\n\n"
                f"{body[:4000]}")
    except Exception as exc:
        return f"[mail] {exc}"


# ── Resend send (as zenith@agm.quest) ────────────────────────────────────────

def _normalize_body(body: str) -> str:
    """Turn escaped newlines the model sometimes passes ('a\\nb') into real ones.

    Shared by every send path (plain, with-attachment, and SMTP) so no caller
    — the orchestrator, email_gateway, reminders — can slip a literal "\n"
    through to the outbound message or the preview. Real newlines pass through
    untouched.
    """
    if not body:
        return body
    import json as _json
    try:
        un = _json.loads('"' + body.replace("'", r"\'") + '"')
        if isinstance(un, str):
            body = un
    except Exception:
        pass
    return body.replace("\\n", "\n").replace("\\r", "")


async def send(to: str, subject: str, body: str, attachment_path: str = "", attachment_paths: list[str] | None = None) -> str:
    """Send an email via Resend's API, with automatic fallback to Gmail SMTP.
    Attach one or more files (attachment_path for a single path, or
    attachment_paths for several)."""
    body = _normalize_body(body)
    paths = list(attachment_paths or [])
    if attachment_path:
        paths.insert(0, attachment_path) if attachment_path not in paths else None
    if paths:
        return await send_with_attachment(to, subject, body, paths)

    resend_err = None
    if _resend_ok():
        payload = {
            "from": settings.resend_from,
            "to": [to],
            "subject": subject,
            "text": body,
        }
        reply_to = settings.resend_reply_to or "zenith@agm.quest"
        payload["reply_to"] = reply_to
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(_RESEND_URL, headers=headers, json=payload)
            if resp.status_code < 400:
                return f"Email sent to {to} from {settings.resend_from}."
            resend_err = f"Resend ({resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            resend_err = f"Resend exception: {exc}"

    # Fallback to Gmail App Password SMTP if Resend fails or is absent
    if _smtp_ok():
        return await send_legacy_smtp(to, subject, body)

    if resend_err:
        return f"[mail] Send failed: {resend_err}"
    return "Email isn't configured for sending (set RESEND_API_KEY or GMAIL_APP_PASSWORD in .env)."


_MAX_ATTACHMENT = 25 * 1024 * 1024  # 25 MB


async def send_with_attachment(to: str, subject: str, body: str, attachment_path, attachment_paths=None) -> str:
    """Send an email with one or more file attachments. Tries Resend first, then SMTP."""
    import base64
    import mimetypes
    import re

    body = _normalize_body(body)

    # Normalize to a list of raw path strings.
    if isinstance(attachment_path, (list, tuple)):
        raws = list(attachment_path)
    elif attachment_paths:
        raws = [attachment_path] + list(attachment_paths)
    elif attachment_path:
        raws = [attachment_path]
    else:
        return f"[mail] No attachment path provided."

    import tempfile
    outdir = Path(tempfile.gettempdir()) / "zenith-files"
    if not outdir.exists() and Path("/tmp/zenith-files").exists():
        outdir = Path("/tmp/zenith-files")

    def resolve_one(raw: str) -> Path:
        raw = (raw or "").strip().strip("'\"")
        m = re.search(r"((?:[A-Za-z]:[\\/]|/tmp/zenith-files/|/)[^\s)]+)", raw)
        if m:
            raw = m.group(1)
        p = Path(raw).expanduser()
        if p.is_file():
            return p
        cand = outdir / p.name
        if cand.is_file():
            return cand
        stem = p.stem.split("_")[0]
        matches = sorted((f for f in outdir.glob(f"{stem}*") if f.is_file()),
                         key=lambda f: f.stat().st_mtime, reverse=True)
        return matches[0] if matches else p

    # Resolve all requested files, keeping the given order.
    paths: list[Path] = []
    seen = set()
    for raw_path in raws:
        p = resolve_one(raw_path)
        if p.is_file() and p not in seen:
            paths.append(p)
            seen.add(p)

    if not paths:
        return f"[mail] Attachment not found: {[a for a in raws]}"

    # Size limit applies per-file and in total.
    total = 0
    for p in paths:
        size = p.stat().st_size
        if size > _MAX_ATTACHMENT:
            return f"[mail] Attachment too large ({size / 1024 / 1024:.1f} MB). Max is 25 MB per file."
        total += size
    if total > _MAX_ATTACHMENT * 4:
        return f"[mail] Total attachments too large ({total / 1024 / 1024:.1f} MB)."

    # Base64 + mime them all up front.
    attachments = []
    for p in paths:
        file_b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        mime_type, _ = mimetypes.guess_type(p.name)
        attachments.append({
            "filename": p.name,
            "content": file_b64,
            "type": mime_type or "application/octet-stream",
        })

    # ── Resend with attachment(s) ───────────────────────────────────────
    resend_err = None
    if _resend_ok():
        payload = {
            "from": settings.resend_from,
            "to": [to],
            "subject": subject,
            "text": body,
            "reply_to": settings.resend_reply_to or "zenith@agm.quest",
            "attachments": [
                {"filename": a["filename"], "content": a["content"]} for a in attachments
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(_RESEND_URL, headers=headers, json=payload)
            if resp.status_code < 400:
                names = ", ".join(a["filename"] for a in attachments)
                return f"Email sent to {to} with attachment(s): {names}."
            resend_err = f"Resend ({resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            resend_err = f"Resend exception: {exc}"

    # ── SMTP fallback with attachment(s) ────────────────────────────────
    if _smtp_ok():
        return await _smtp_send_with_attachment(to, subject, body, paths)

    if resend_err:
        return f"[mail] Send-with-attachment failed: {resend_err}"
    return "Email isn't configured for sending."


async def _smtp_send_with_attachment(
    to: str, subject: str, body: str, file_paths,
) -> str:
    """SMTP send with MIME multipart attachment(s). `file_paths` is a single
    Path or a list of Paths."""
    if not _smtp_ok():
        return "No SMTP configured."
    host = settings.mail_smtp_host or "smtp.gmail.com"
    user = settings.gmail_user or settings.mail_smtp_user
    password = settings.gmail_app_password or settings.mail_smtp_pass
    try:
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders
        import mimetypes
    except ImportError:
        return "[mail] MIME modules unavailable."

    paths = [file_paths] if isinstance(file_paths, Path) else list(file_paths)

    try:
        msg = MIMEMultipart()
        msg["From"] = f"Zenith <{user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        for fp in paths:
            file_bytes = fp.read_bytes()
            mime_type, _ = mimetypes.guess_type(fp.name)
            maintype, subtype = (mime_type.split("/", 1) if mime_type and "/" in mime_type
                                 else ("application", "octet-stream"))
            part = MIMEBase(maintype, subtype)
            part.set_payload(file_bytes)
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{fp.name}"')
            msg.attach(part)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _smtp_send, host, 587, user, password, to, msg)
        names = ", ".join(fp.name for fp in paths)
        return f"Email sent to {to} with attachment(s): {names} via Gmail SMTP."
    except Exception as exc:
        return f"[mail] SMTP send-with-attachment failed: {exc}"


def _smtp_ok() -> bool:
    user = settings.gmail_user or settings.mail_smtp_user
    password = settings.gmail_app_password or settings.mail_smtp_pass
    return bool(user and password)


async def send_legacy_smtp(to: str, subject: str, body: str) -> str:
    """SMTP send via Gmail App Password or configured SMTP server."""
    body = _normalize_body(body)
    if not _smtp_ok():
        return "No SMTP configured."
    host = settings.mail_smtp_host or "smtp.gmail.com"
    user = settings.gmail_user or settings.mail_smtp_user
    password = settings.gmail_app_password or settings.mail_smtp_pass
    try:
        import smtplib
        from email.message import EmailMessage
    except ImportError:
        return "[mail] smtplib unavailable."
    try:
        msg = EmailMessage()
        msg["From"] = f"Zenith <{user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _smtp_send,
            host, 587, user, password, to, msg,
        )
        return f"Email sent to {to} via Gmail SMTP."
    except Exception as exc:
        return f"[mail] SMTP send failed: {exc}"


def _smtp_send(host, port, user, password, to, msg):
    import smtplib
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
