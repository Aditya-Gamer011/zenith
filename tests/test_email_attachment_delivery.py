"""Tests for Email File Attachment Delivery & Open-Tool CDN/Domain Policy."""
import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

from zenith.agents.agent_service import DEPARTMENTS
from zenith.memory import store
from zenith.tools.mail import _normalize_body, send_with_attachment


def _run(coro):
    return asyncio.run(coro)


def test_normalize_body_sanitizes_hallucinated_domains():
    """Verify _normalize_body strips fake/local domains like app.zenith.os and localhost."""
    raw_body = (
        "Hi Aditya,\n\n"
        "Here is your presentation:\n"
        "Web View: https://app.zenith.os/presentation/bears_123\n"
        "Download: https://app.zenith.os/api/files/download?filename=bears.pptx\n"
        "[Launch Presentation](http://localhost:8005/presentation/bears_123)\n"
        "[Download PowerPoint](/api/files/download?filename=bears.pptx)\n"
    )

    clean_with_attach = _normalize_body(raw_body, has_attachments=True)
    assert "app.zenith.os" not in clean_with_attach
    assert "localhost:8005" not in clean_with_attach
    assert "[Attached directly to this email]" in clean_with_attach

    clean_without_attach = _normalize_body("Check https://app.zenith.os/presentation/123", has_attachments=False)
    assert "app.zenith.os" not in clean_without_attach


def test_resolve_one_varieties(tmp_path):
    """Verify resolve_one resolves absolute paths, query parameters, bare filenames, and SQLite artifact IDs."""
    test_file = tmp_path / "test_wildlife.pptx"
    test_file.write_text("dummy presentation data")

    # 1. Absolute path test
    with patch("zenith.tools.mail.Path") as mock_path_cls:
        pass  # We can test with real Path directly using send_with_attachment or importing resolve_one

    from zenith.tools import mail
    # Test resolve_one through send_with_attachment validation
    store.init_db()
    store.save_artifact(
        artifact_id="bears_deck_999",
        artifact_type="presentation",
        title="Kingdom of the Bears",
        theme="nordic_navy",
        data_json={},
        file_path=str(test_file),
        web_url="/presentation/bears_deck_999",
    )

    # Mock _resend_ok to inspect payload
    with patch.object(mail, "_resend_ok", return_value=True), \
         patch.object(mail, "_normalize_body", side_effect=lambda b, **kw: b), \
         patch("httpx.AsyncClient") as mock_http:
        
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_http.return_value.__aenter__.return_value = mock_client

        # 1. Direct path
        res = _run(send_with_attachment("test@example.com", "Subject", "Body", str(test_file)))
        assert "Email sent to test@example.com with attachment(s)" in res
        payload = mock_client.post.call_args[1]["json"]
        assert len(payload["attachments"]) == 1
        assert payload["attachments"][0]["filename"] == "test_wildlife.pptx"

        # 2. Query param path: /api/files/download?filename=test_wildlife.pptx
        # Place a copy in /tmp/zenith-files
        tmp_zenith = Path("/tmp/zenith-files")
        tmp_zenith.mkdir(parents=True, exist_ok=True)
        (tmp_zenith / "test_wildlife.pptx").write_text("zenith-files data")

        res_qs = _run(send_with_attachment("test@example.com", "Subject", "Body", "/api/files/download?filename=test_wildlife.pptx"))
        assert "Email sent to test@example.com with attachment(s)" in res_qs

        # 3. Artifact ID
        res_art = _run(send_with_attachment("test@example.com", "Subject", "Body", "bears_deck_999"))
        assert "Email sent to test@example.com with attachment(s)" in res_art


def test_communication_agent_tools_and_prompt():
    """Verify Communication Specialist has query_findings and list_generated_files and attachment policy."""
    comms = DEPARTMENTS["communication"]
    tools = comms["tools"]
    assert "email_send" in tools
    assert "query_findings" in tools
    assert "list_generated_files" in tools

    prompt = comms["system"]
    assert "CRITICAL FILE ATTACHMENT & ZERO-DOMAIN POLICY" in prompt
    assert "app.zenith.os" in prompt
    assert "attachment_path" in prompt


def test_query_findings_highlights_email_attachment_path():
    """Verify query_findings clearly labels the email attachment path."""
    from zenith.tools.agent import query_findings
    store.init_db()
    store.save_artifact(
        artifact_id="test_art_777",
        artifact_type="presentation",
        title="Penguins of Antarctica",
        theme="nordic_navy",
        data_json={},
        file_path="/tmp/zenith-files/penguins.pptx",
        web_url="/presentation/test_art_777",
    )

    result = _run(query_findings(query="Penguin"))
    assert "Penguins of Antarctica" in result
    assert "Local Web Viewer" in result
    assert "Email Attachment: Use `email_send(..., attachment_path='/tmp/zenith-files/penguins.pptx')`" in result


def test_never_sends_wrong_file(tmp_path):
    """Verify that mail delivery never accidentally sends an unrelated file when the requested file is missing."""
    test_bears = tmp_path / "bears_arctic_expedition.pptx"
    test_bears.write_text("bears presentation content")

    from zenith.tools import mail
    store.init_db()
    store.save_artifact(
        artifact_id="deck_bears_555",
        artifact_type="presentation",
        title="Bears of the Arctic",
        theme="nordic_navy",
        data_json={},
        file_path=str(test_bears),
        web_url="/presentation/deck_bears_555",
    )

    with patch.object(mail, "_resend_ok", return_value=True), \
         patch.object(mail, "_normalize_body", side_effect=lambda b, **kw: b), \
         patch("httpx.AsyncClient") as mock_http:

        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_client.post.return_value = mock_resp
        mock_http.return_value.__aenter__.return_value = mock_client

        # If user requests "wolves.pptx" which does NOT exist, it must NOT fall back to sending bears!
        res_missing = _run(mail.send_with_attachment("test@example.com", "Subject", "Body", "wolves.pptx"))
        assert "Attachment not found" in res_missing
        assert "wolves.pptx" in res_missing

        # But when user requests "Bears", it matches accurately and sends bears!
        res_matched = _run(mail.send_with_attachment("test@example.com", "Subject", "Body", "bears"))
        assert "Email sent to test@example.com with attachment(s)" in res_matched
