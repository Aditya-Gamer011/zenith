"""Tests for Resend Outbound Enforcement and Personal Email Protection."""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

from zenith.core.config import settings
from zenith.tools import mail
from zenith.core.tools import tool_email_send
from zenith.core.prompts import build_system_prompt
from zenith.agents.agent_service import DEPARTMENTS


def _run(coro):
    return asyncio.run(coro)


def test_resend_is_primary_outbound_and_uses_assigned_email():
    """Verify mail.send uses Resend and transmits from settings.resend_from."""
    with patch.object(mail, "_resend_ok", return_value=True), \
         patch("httpx.AsyncClient") as mock_http:

        mock_client = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_client.post.return_value = mock_resp
        mock_http.return_value.__aenter__.return_value = mock_client

        res = _run(mail.send("recipient@example.com", "Test Subject", "Hello"))
        assert "Email sent to recipient@example.com" in res
        assert settings.resend_from in res
        assert "via Resend" in res

        # Verify exact payload sent to Resend API
        post_kwargs = mock_client.post.call_args
        payload = post_kwargs[1]["json"]
        assert payload["from"] == settings.resend_from
        assert payload["to"] == ["recipient@example.com"]
        assert payload["subject"] == "Test Subject"
        assert payload["text"] == "Hello"
        assert payload["reply_to"] == (settings.resend_reply_to or "zenith@agm.quest")


def test_resend_failure_never_falls_back_to_user_gmail():
    """Verify that when Resend fails, it reports the error and NEVER falls back to personal Gmail."""
    with patch.object(mail, "_resend_ok", return_value=True), \
         patch.object(mail, "_smtp_ok", return_value=True), \
         patch.object(mail, "send_legacy_smtp", new_callable=AsyncMock) as mock_smtp, \
         patch("httpx.AsyncClient") as mock_http:

        mock_client = AsyncMock()
        mock_resp = MagicMock(status_code=422, text="Domain not verified")
        mock_client.post.return_value = mock_resp
        mock_http.return_value.__aenter__.return_value = mock_client

        res = _run(mail.send("recipient@example.com", "Test Subject", "Hello"))
        assert "[mail] Send failed via Resend" in res
        assert "Resend (422)" in res
        # Legacy SMTP was NEVER called
        assert mock_smtp.call_count == 0


def test_smtp_ok_ignores_imap_credentials():
    """Verify _smtp_ok is False when only GMAIL_USER/GMAIL_APP_PASSWORD are set for IMAP."""
    with patch.object(settings, "gmail_user", "personal@gmail.com"), \
         patch.object(settings, "gmail_app_password", "secretpass"), \
         patch.object(settings, "mail_smtp_host", ""):

        assert mail._smtp_ok() is False


def test_tool_email_send_ignores_hallucinated_from_kwargs():
    """Verify tool_email_send ignores any 'from' or 'from_email' kwargs passed by an LLM."""
    with patch.object(mail, "_resend_ok", return_value=True), \
         patch("httpx.AsyncClient") as mock_http:

        mock_client = AsyncMock()
        mock_resp = MagicMock(status_code=200)
        mock_client.post.return_value = mock_resp
        mock_http.return_value.__aenter__.return_value = mock_client

        res = _run(tool_email_send(
            to="friend@example.com",
            subject="Presentation",
            body="Attached presentation",
            from_email="user@personal.com",
            sender="user@personal.com",
        ))

        assert "Email sent to friend@example.com" in res
        payload = mock_client.post.call_args[1]["json"]
        assert payload["from"] == settings.resend_from
        assert "user@personal.com" not in payload["from"]


def test_prompts_and_agents_instruct_resend_outbound():
    """Verify system prompts and communication specialist enforce Resend outbound policy."""
    sys_prompt = build_system_prompt()
    assert settings.resend_from in sys_prompt
    assert "Resend" in sys_prompt
    assert "NEVER attempt, claim, or pretend to send emails from" in sys_prompt

    comm_prompt = DEPARTMENTS["communication"]["system"]
    assert "CRITICAL OUTBOUND SENDER DIRECTIVE" in comm_prompt
    assert settings.resend_from in comm_prompt
    assert "exclusively via Resend" in comm_prompt
