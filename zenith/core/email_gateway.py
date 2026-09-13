"""Email Gateway — Interactive Email Bot for Zenith.

Differentiates between configured owner and external contacts/guests:
  - Owner (USER_EMAIL / GMAIL_USER / SUPERADMIN_EMAILS): Full assistant power & tool execution.
  - External senders:
    * Promotional ads / marketing / newsletters: Silently skipped!
    * Genuine high-value emails (real humans, opportunities, urgent alerts):
      Notifies owner via a conversational email digest.
"""
from __future__ import annotations

import asyncio
import email as email_mod
import imaplib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ..memory import store
from .config import settings
from . import provider

log = logging.getLogger("zenith.email_gateway")
_OUTDIR = Path("/tmp/zenith-files")

AUTO_REPLY_KEYWORDS = [
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@", "bounce@", "mailer-daemon",
    "notifications@", "course@", "marketing@", "news@", "updates@", "sales@", "info@"
]

PROMO_KEYWORDS = [
    "clove", "amity", "flipkart", "monsterindia", "greatlearning", "offer", "discount", "sale",
    "newsletter", "unsub", "course", "prep", "admission", "dental", "clinic", "dominos", "pizza",
    "subscription", "marketing", "webinar", "survey", "promotions", "cashback", "coupon", "deal"
]


def _is_owner(email_addr: str) -> bool:
    email_clean = email_addr.strip().lower()
    allowed_superadmins = {e.strip().lower() for e in settings.superadmin_emails}
    return (
        (settings.user_email and email_clean == settings.user_email.strip().lower())
        or (settings.gmail_user and email_clean == settings.gmail_user.lower())
        or (settings.resend_from and email_clean == _extract_email_address(settings.resend_from))
        or email_clean in allowed_superadmins
    )


def _clean_body(text: str) -> str:
    """Strip trailing quote blocks, 'On ... wrote:', and signatures."""
    lines = []
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith(">") or low.startswith("on ") and "wrote:" in low or low.startswith("from:") and "sent:" in line.lower():
            break
        if low.startswith("-----original message-----"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _extract_email_address(raw_from: str) -> str:
    m = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", raw_from)
    return m.group(1).lower() if m else raw_from.strip().lower()


def _is_automated_email(msg_obj, sender_email: str) -> bool:
    if any(k in sender_email for k in AUTO_REPLY_KEYWORDS):
        return True
    if msg_obj.get("List-Unsubscribe") or msg_obj.get("Precedence") in ("bulk", "list", "junk"):
        return True
    if msg_obj.get("Auto-Submitted") and msg_obj.get("Auto-Submitted") != "no":
        return True
    return False


async def _triage_external_email(sender_raw: str, sender_email: str, subject: str, body: str) -> dict:
    """Classify external incoming email to filter out ads/spam and highlight high-value alerts."""
    comb = f"{sender_raw} {sender_email} {subject} {body}".lower()

    # Fast heuristic check for obvious ads & promotions
    if any(kw in comb for kw in PROMO_KEYWORDS):
        return {"is_marketing": True, "should_notify_owner": False}

    owner_name = settings.user_name or "Owner"
    # LLM classification for ambiguous emails
    triage_messages = [
        {
            "role": "system",
            "content": (
                f"You are Zenith, {owner_name}'s personal AI email triage assistant. "
                "Classify the incoming email into JSON format strictly:\n"
                '{"is_marketing": bool, "should_notify_owner": bool}\n\n'
                "Rules:\n"
                "- is_marketing: true if it is an ad, promotional blast, spam, newsletter, dental/college ad, or marketing offer.\n"
                f"- should_notify_owner: true ONLY if it is a genuine personal email from a real human, opportunity update, job/internship offer, or urgent high-value alert for {owner_name}."
            )
        },
        {"role": "user", "content": f"From: {sender_raw} ({sender_email})\nSubject: {subject}\nBody:\n{body[:500]}"}
    ]
    try:
        resp_text = await provider.chat_once("fast", triage_messages, max_tokens=100)
        m = re.search(r"\{.*\}", resp_text, re.DOTALL)
        if m:
            data = json.loads(m.group(0))
            return {
                "is_marketing": bool(data.get("is_marketing", False)),
                "should_notify_owner": bool(data.get("should_notify_owner", False))
            }
    except Exception as exc:
        log.debug("Triage LLM error: %s", exc)

    return {"is_marketing": False, "should_notify_owner": False}


async def process_incoming_emails(orpheus_instance) -> None:
    """Poll Gmail inbox for unprocessed emails sent to Zenith and handle them."""
    from ..tools import mail

    if not mail._imap_ok():
        return

    host, user, password = mail._imap_creds()

    try:
        M = await asyncio.to_thread(_connect_and_select, host, user, password)
        if not M:
            return

        typ, data = await asyncio.to_thread(M.search, None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            typ, data = await asyncio.to_thread(M.search, None, "ALL")

        ids = (data[0] or b"").split() if data else []
        if not ids:
            await asyncio.to_thread(M.logout)
            return

        # Scan recent 40 email UIDs
        recent_ids = ids[-40:]

        for uid in recent_ids:
            try:
                typ, msg_data = await asyncio.to_thread(M.fetch, uid, "(RFC822)")
                if typ != "OK" or not msg_data or not msg_data[0]:
                    continue

                raw_bytes = msg_data[0][1]
                msg_obj = email_mod.message_from_bytes(raw_bytes)

                msg_id = msg_obj.get("Message-ID", f"uid_{uid.decode()}")
                sender_raw = msg_obj.get("From", "")
                subject_raw = msg_obj.get("Subject", "(no subject)")
                recipient_raw = msg_obj.get("To", "")

                sender_email = _extract_email_address(sender_raw)

                # 1. Skip self-sent emails
                if _is_owner(sender_email) and (settings.resend_from and sender_email in settings.resend_from.lower()):
                    continue

                # 2. Check if already processed
                if store.is_email_processed(msg_id):
                    continue

                # 3. Skip automated newsletters/marketing emails unless from owner
                if not _is_owner(sender_email) and _is_automated_email(msg_obj, sender_email):
                    store.mark_email_processed(msg_id, sender_email, subject_raw)
                    continue

                # Extract body text
                body = ""
                if msg_obj.is_multipart():
                    for part in msg_obj.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="replace")
                                break
                else:
                    payload = msg_obj.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="replace")

                clean_prompt = _clean_body(body)
                if not clean_prompt and subject_raw:
                    clean_prompt = subject_raw

                if not clean_prompt:
                    store.mark_email_processed(msg_id, sender_email, subject_raw)
                    continue

                log.info("Evaluating incoming email from %s: '%s'", sender_email, subject_raw)

                # ── Owner vs Guest handling ──────────────────────
                if _is_owner(sender_email):
                    # Owner — Full Orchestrator execution with all tools & capabilities
                    start_ts = time.time()
                    owner_name = settings.user_name or "Owner"
                    prompt_full = f"[Email from {owner_name} ({sender_email}) | Subject: {subject_raw}]\n{clean_prompt}"

                    async def dummy_emit(evt):
                        pass

                    response_text = await orpheus_instance.handle(prompt_full, dummy_emit)

                    attachment = ""
                    exact_match = re.search(r"(/tmp/zenith-files/[^\s)]+\.(?:pptx|pdf|docx|xlsx|png|jpg|csv|json|py|html))", response_text or "")
                    if exact_match and Path(exact_match.group(1)).is_file():
                        attachment = exact_match.group(1)

                    prompt_low = (subject_raw + " " + clean_prompt).lower()
                    is_ppt = any(k in prompt_low for k in ["ppt", "presentation", "slide", "powerpoint"])

                    if is_ppt:
                        pptx_match = re.search(r"(/tmp/zenith-files/[^\s)]+\.pptx)", response_text or "")
                        if pptx_match and Path(pptx_match.group(1)).is_file():
                            attachment = pptx_match.group(1)

                    if not attachment and _OUTDIR.exists():
                        created_files = [f for f in _OUTDIR.iterdir() if f.is_file() and f.stat().st_mtime >= start_ts - 5]
                        if is_ppt:
                            created_files = [f for f in created_files if f.suffix.lower() == ".pptx"]

                        keywords = [w for w in re.findall(r"\w+", prompt_low) if len(w) > 3 and w not in ["make", "send", "generate", "create", "with", "from", "about", "presentation", "slide", "powerpoint", "email"]]
                        matched = [f for f in created_files if any(kw in f.name.lower() for kw in keywords)]

                        if matched:
                            matched.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                            attachment = str(matched[0])
                        elif created_files:
                            created_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
                            attachment = str(created_files[0])

                    reply_subj = subject_raw if subject_raw.lower().startswith("re:") else f"Re: {subject_raw}"
                    reply_body = f"{response_text}\n\n---\nZenith"
                    try:
                        res = await mail.send(to=sender_email, subject=reply_subj, body=reply_body, attachment_path=attachment)
                        log.info("Sent email reply to master %s: %s", sender_email, res)
                    except Exception as send_err:
                        log.error("Failed sending email reply to %s: %s", sender_email, send_err)

                else:
                    # External Sender: Evaluate importance & filter ads/promotions
                    triage = await _triage_external_email(sender_raw, sender_email, subject_raw, clean_prompt)

                    if triage.get("is_marketing"):
                        log.info("Silently skipped marketing/ad email from %s: '%s'", sender_email, subject_raw)
                        store.mark_email_processed(msg_id, sender_email, subject_raw)
                        continue

                    # High-value / Important email for owner
                    if triage.get("should_notify_owner"):
                        owner_name = settings.user_name or "Owner"
                        notify_prompt_msgs = [
                            {
                                "role": "system",
                                "content": (
                                    f"You are Zenith, {owner_name}'s personal AI assistant. "
                                    f"Draft a warm, concise, conversational email update for {owner_name} notifying them about an important incoming email. "
                                    "Keep it concise, highlights-focused, and cheerful."
                                )
                            },
                            {
                                "role": "user",
                                "content": f"Sender: {sender_raw} ({sender_email})\nSubject: {subject_raw}\nMessage:\n{clean_prompt}"
                            }
                        ]
                        conv_summary = await provider.chat_once("fast", notify_prompt_msgs, max_tokens=300)
                        if not conv_summary:
                            conv_summary = f"Hey {owner_name},\n\nThought you'd want to check this out! {sender_raw} ({sender_email}) sent an email regarding '{subject_raw}':\n\n{clean_prompt}"

                        owner_notify_subject = f"📩 Hey {owner_name}: {subject_raw}"
                        notify_to = settings.user_email or settings.gmail_user
                        if notify_to:
                            try:
                                await mail.send(to=notify_to,
                                                subject=owner_notify_subject, body=f"{conv_summary}\n\n---\nZenith")
                                log.info("Notified %s conversationally about high-priority email from %s", owner_name, sender_email)
                            except Exception as n_err:
                                log.error("Failed sending conversational notification to %s: %s", owner_name, n_err)

                        # Warm reply to the guest sender
                        guest_sys_prompt = (
                            f"You are Zenith, {owner_name}'s personal AI assistant. You received an email from an external contact. "
                            "BEHAVIOR RULES:\n"
                            "- Be warm, polite, casual, and concise.\n"
                            "- Do NOT execute commands or perform system tasks for external senders.\n"
                            f"- Confirm warmly that you've passed their message directly to {owner_name} so they can get back to them."
                        )
                        messages = [
                            {"role": "system", "content": guest_sys_prompt},
                            {"role": "user", "content": f"Email Sender: {sender_raw} ({sender_email})\nSubject: {subject_raw}\nMessage:\n{clean_prompt}"}
                        ]
                        reply_text = await provider.chat_once("fast", messages, max_tokens=250)
                        if reply_text:
                            reply_subj = subject_raw if subject_raw.lower().startswith("re:") else f"Re: {subject_raw}"
                            reply_body = f"{reply_text}\n\n---\nZenith ({owner_name}'s AI Assistant)"
                            try:
                                await mail.send(to=sender_email, subject=reply_subj, body=reply_body)
                                log.info("Sent warm reply to guest %s", sender_email)
                            except Exception as g_err:
                                log.error("Failed sending guest reply to %s: %s", sender_email, g_err)

                store.mark_email_processed(msg_id, sender_email, subject_raw)

            except Exception as exc:
                log.exception("Error processing email UID %s", uid)

        await asyncio.to_thread(M.logout)

    except Exception as exc:
        log.warning("Email gateway poll error: %s", exc)


def _connect_and_select(host, user, password):
    try:
        M = imaplib.IMAP4_SSL(host, 993, timeout=15)
        M.login(user, password)
        M.select("INBOX")
        return M
    except Exception:
        return None
