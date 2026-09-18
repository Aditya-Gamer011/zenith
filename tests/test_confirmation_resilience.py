"""Tests for Confirmation Gate Resilience, Tab Switch Decoupling, and Optional Approvals Setting."""
import asyncio
from unittest.mock import patch, MagicMock
import pytest

from zenith.core.config import settings
from zenith.core.confirmation import ConfirmGate, confirm_tools, _DEFAULT_CONFIRM_TOOLS
from zenith.core.setup import SECRETS_CATALOG, get_catalog_with_values


def _run(coro):
    return asyncio.run(coro)


def test_confirm_tools_respects_require_approvals_setting():
    """Verify confirm_tools() is empty when require_approvals is False and active when True."""
    # When require_approvals is False -> all approvals bypassed (autonomous mode)
    with patch.object(settings, "require_approvals", False):
        assert confirm_tools() == ()

    # When require_approvals is True -> returns full default confirm tools tuple
    with patch.object(settings, "require_approvals", True):
        assert confirm_tools() == _DEFAULT_CONFIRM_TOOLS
        assert "email_send" in confirm_tools()


def test_confirm_gate_get_pending_and_resolve():
    """Verify ConfirmGate tracks pending confirmations and allows resolution across reconnects."""
    gate = ConfirmGate(timeout=5.0)

    async def _test():
        # Start a request in background
        task = asyncio.create_task(gate.request("email_send", {"to": "aditya@example.com"}))
        await asyncio.sleep(0.01)

        # 1. Verify get_pending returns the pending gate
        pending_list = gate.get_pending()
        assert len(pending_list) == 1
        cid = pending_list[0]["id"]
        assert pending_list[0]["tool"] == "email_send"
        assert "email_send" in pending_list[0]["message"]

        # 2. Resolve the confirmation
        ok = gate.resolve(cid, True)
        assert ok is True

        # 3. Verify the request returned True (approved)
        result = await task
        assert result is True

        # 4. Verify get_pending is now empty
        assert len(gate.get_pending()) == 0

        # 5. Resolving an expired/already completed ID returns False cleanly
        assert gate.resolve(cid, True) is False

    _run(_test())


def test_setup_catalog_includes_require_approvals_switch():
    """Verify SECRETS_CATALOG registers REQUIRE_APPROVALS under security category."""
    items = get_catalog_with_values()
    keys = {item["key"]: item for item in items}
    assert "REQUIRE_APPROVALS" in keys
    item = keys["REQUIRE_APPROVALS"]
    assert item["category"] == "security"
    assert item["field_type"] == "switch"
    assert "Approvals" in item["label"]
