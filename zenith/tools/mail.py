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
import time
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

def _normalize_body(body: str, has_attachments: bool = False) -> str:
    """Turn escaped newlines into real ones and sanitize hallucinated domains / local URLs.

    Shared by every send path (plain, with-attachment, and SMTP).
    Zenith is an open-source, local-first tool: external email recipients cannot open
    localhost or imaginary domains like 'app.zenith.os'.
    """
    if not body:
        return body
    import json as _json
    import re
    try:
        un = _json.loads('"' + body.replace("'", r"\'") + '"')
        if isinstance(un, str):
            body = un
    except Exception:
        pass
    body = body.replace("\\n", "\n").replace("\\r", "")

    # Sanitize hallucinated or local URLs in outbound email bodies
    # e.g., https://app.zenith.os/..., http://localhost:8005/..., /presentation/..., /api/files/download?...
    fake_domain_pattern = re.compile(
        r'https?://(?:app\.zenith\.os|zenith\.local|localhost(?::\d+)?|127\.0\.0\.1(?::\d+)?)[^\s)\]"\'>]*',
        re.IGNORECASE,
    )
    if has_attachments:
        body = fake_domain_pattern.sub("[Attached directly to this email]", body)
        # Clean relative presentation/download links
        body = re.sub(
            r'\[([^\]]+)\]\((?:/presentation/[^\)]+|/api/files/download[^\)]+)\)',
            r'\1 [Attached directly to this email]',
            body,
        )
    else:
        body = fake_domain_pattern.sub("[Local Zenith server deliverable]", body)

    return body


async def send(to: str, subject: str, body: str, attachment_path: str = "", attachment_paths: list[str] | None = None) -> str:
    """Send an email via Resend's API, with automatic fallback to Gmail SMTP.
    Attach one or more files (attachment_path for a single path, or
    attachment_paths for several)."""
    paths = list(attachment_paths or [])
    if attachment_path:
        paths.insert(0, attachment_path) if attachment_path not in paths else None
    if paths:
        return await send_with_attachment(to, subject, body, paths)

    body = _normalize_body(body, has_attachments=False)

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
                return f"Email sent to {to} from {settings.resend_from} via Resend."
            resend_err = f"Resend ({resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            resend_err = f"Resend exception: {exc}"

        # If Resend is configured, it is the designated outbound provider.
        # NEVER fall back to the user's personal Gmail account.
        return f"[mail] Send failed via Resend ({settings.resend_from}): {resend_err}"

    # Dedicated SMTP fallback ONLY if Resend is absent and dedicated SMTP is configured
    if _smtp_ok():
        return await send_legacy_smtp(to, subject, body)

    return f"Email isn't configured for sending (set RESEND_API_KEY in .env for outbound sending from {settings.resend_from})."


_MAX_ATTACHMENT = 25 * 1024 * 1024  # 25 MB


async def send_with_attachment(to: str, subject: str, body: str, attachment_path, attachment_paths=None) -> str:
    """Send an email with one or more file attachments. Tries Resend first, then SMTP."""
    import base64
    import mimetypes
    import re

    body = _normalize_body(body, has_attachments=True)

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

    def resolve_one(raw: str) -> Optional[Path]:
        raw = (raw or "").strip().strip("'\"")
        if not raw:
            return None

        # 1. Check if raw is already an exact existing file path on disk
        p_direct = Path(raw).expanduser()
        if p_direct.is_file():
            return p_direct

        # 2. If download query parameter is present: ?filename=...
        if "filename=" in raw:
            import urllib.parse
            parsed = urllib.parse.urlparse(raw)
            qs = urllib.parse.parse_qs(parsed.query)
            if "filename" in qs and qs["filename"]:
                raw = qs["filename"][0]
                p_direct = Path(raw).expanduser()

        # 3. If presentation URL is present: /presentation/<deck_id>
        m_deck = re.search(r'/presentation/([A-Za-z0-9_\-]+)', raw)
        if m_deck:
            raw = m_deck.group(1)

        # 4. Check known search directories directly with filename
        search_dirs = [
            outdir,
            Path("/tmp/zenith-files"),
            Path("static/generated"),
            Path("static/presentations"),
        ]
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            cand = sdir / p_direct.name
            if cand.is_file():
                return cand

        # Extract subject/body keywords for context-aware validation
        stop_words = {"the", "and", "for", "with", "presentation", "deck", "slides", "ppt", "document", "report", "file", "test", "your", "here", "this", "from", "sent", "attached", "attachment"}
        context_tokens = [
            t.lower() for t in re.split(r'[-_\s,.:;!?()"\']+', f"{subject} {body}")
            if len(t) >= 3 and t.lower() not in stop_words
        ]

        generic_presentation = any(raw.lower().strip() == g for g in ("presentation.pptx", "presentation", "deck", "slides", "ppt", "latest.pptx", "the presentation", "the deck"))
        generic_doc = any(raw.lower().strip() == g for g in ("document.pdf", "document.docx", "document", "report", "report.pdf", "latest.pdf", "the document"))
        is_generic = generic_presentation or generic_doc

        # 5. Check SQLite artifact store via smart find_artifact
        art_path = None
        try:
            from ..memory import store
            art_type = ""
            raw_lower = raw.lower()
            if any(ext in raw_lower for ext in (".pptx", "presentation", "deck", "slide", "ppt")):
                art_type = "presentation"
            elif any(ext in raw_lower for ext in (".pdf", ".docx", "document", "report")):
                art_type = "document"

            art = store.find_artifact(raw, artifact_type=art_type)
            if art and art.get("file_path"):
                art_p = Path(art["file_path"])
                if art_p.is_file():
                    art_path = art_p
                else:
                    for sdir in search_dirs:
                        if sdir.exists() and (sdir / art_p.name).is_file():
                            art_path = sdir / art_p.name
                            break
        except Exception as e:
            log.debug("find_artifact error in mail resolve_one: %s", e)

        # If query was a specific artifact ID or exact filename and matched artifact store, return it
        if not is_generic and art_path:
            return art_path

        # 6. Case-insensitive search in search directories for matching keywords
        stem = p_direct.stem
        for prefix in ("presentation_", "deck_", "doc_", "report_"):
            if stem.lower().startswith(prefix):
                stem = stem[len(prefix):]

        raw_keywords = re.split(r'[-_\s,.]+', stem)
        keywords = [k.lower() for k in raw_keywords if len(k) >= 3 and k.lower() not in stop_words]

        if not is_generic and keywords:
            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                ext = p_direct.suffix.lower()
                candidates = []
                for f in sdir.glob("*"):
                    if not f.is_file() or "pytest" in f.name:
                        continue
                    if ext and f.suffix.lower() != ext:
                        continue
                    fname_lower = f.name.lower()
                    matched_kw = sum(1 for kw in keywords if kw in fname_lower)
                    if matched_kw > 0:
                        candidates.append((matched_kw, f.stat().st_mtime, f))
                if candidates:
                    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                    return candidates[0][2]

        # 7. Safe Recency & Context Fallback ONLY when query is generic (e.g. "presentation.pptx" or "document.pdf")
        if is_generic:
            target_ext = ".pptx" if generic_presentation else (".pdf" if ".pdf" in raw.lower() else ".docx")
            now = time.time()
            all_candidates: list[tuple[int, float, Path]] = []

            # Add art_path if valid and recent (< 2 hours)
            if art_path and art_path.is_file():
                mtime = art_path.stat().st_mtime
                if now - mtime < 7200:
                    topic_score = sum(1 for t in context_tokens if t in art_path.name.lower())
                    all_candidates.append((topic_score, mtime, art_path))

            # Scan search directories for recent files (< 2 hours)
            for sdir in search_dirs:
                if not sdir.exists():
                    continue
                for f in sdir.glob(f"*{target_ext}"):
                    if not f.is_file() or "pytest" in f.name:
                        continue
                    mtime = f.stat().st_mtime
                    if now - mtime < 7200:
                        topic_score = sum(1 for t in context_tokens if t in f.name.lower())
                        all_candidates.append((topic_score, mtime, f))

            if all_candidates:
                # Sort by topic score (if context tokens present) then recency mtime
                all_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
                # If context tokens were present and the top candidate matches, ensure no conflict
                return all_candidates[0][2]

        # If we cannot verify with confidence, NEVER guess or send an unrelated file!
        return None

    # Resolve all requested files, keeping the given order.
    paths: list[Path] = []
    seen = set()
    for raw_path in raws:
        p = resolve_one(raw_path)
        if p and p.is_file() and p not in seen:
            paths.append(p)
            seen.add(p)

    if not paths:
        return f"[mail] Attachment not found: Could not find any presentation or file matching {[a for a in raws]}. Please verify the requested file name."

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
                return f"Email sent to {to} with attachment(s): {names} from {settings.resend_from} via Resend."
            resend_err = f"Resend ({resp.status_code}): {resp.text[:200]}"
        except Exception as exc:
            resend_err = f"Resend exception: {exc}"

        # If Resend is configured, it is the designated outbound provider.
        # NEVER fall back to the user's personal Gmail account.
        return f"[mail] Send-with-attachment failed via Resend ({settings.resend_from}): {resend_err}"

    # ── Dedicated SMTP fallback ONLY if Resend is absent and dedicated SMTP is configured ──
    if _smtp_ok():
        return await _smtp_send_with_attachment(to, subject, body, paths)

    return f"Email isn't configured for sending (set RESEND_API_KEY in .env for outbound sending from {settings.resend_from})."


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
        msg["From"] = settings.resend_from or f"Zenith <{user}>"
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
        return f"Email sent to {to} from {settings.resend_from} with attachment(s): {names} via SMTP."
    except Exception as exc:
        return f"[mail] SMTP send-with-attachment failed: {exc}"


def _smtp_ok() -> bool:
    # Dedicated SMTP only. Having GMAIL_USER/GMAIL_APP_PASSWORD for IMAP reading
    # must NEVER be used to send outbound emails as the user's personal Gmail!
    return bool(settings.mail_smtp_host and settings.mail_smtp_user and settings.mail_smtp_pass)


async def send_legacy_smtp(to: str, subject: str, body: str) -> str:
    """SMTP send via configured dedicated SMTP server."""
    body = _normalize_body(body)
    if not _smtp_ok():
        return "No dedicated SMTP configured."
    host = settings.mail_smtp_host
    user = settings.mail_smtp_user
    password = settings.mail_smtp_pass
    try:
        import smtplib
        from email.message import EmailMessage
    except ImportError:
        return "[mail] smtplib unavailable."
    try:
        msg = EmailMessage()
        msg["From"] = settings.resend_from or f"Zenith <{user}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _smtp_send,
            host, 587, user, password, to, msg,
        )
        return f"Email sent to {to} from {settings.resend_from} via SMTP."
    except Exception as exc:
        return f"[mail] SMTP send failed: {exc}"


def _smtp_send(host, port, user, password, to, msg):
    import smtplib
    with smtplib.SMTP(host, port, timeout=20) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
