"""Zenith — Art & Design Integrations Test Suite.

Tests OAuth state validation, token lifecycle, tool schema validation,
and plugin bridge command dispatch.

Run:  python -m pytest tests/test_integrations.py -v
"""
from __future__ import annotations

import asyncio
import hashlib
import base64
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. OAuth State Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFigmaOAuthState(unittest.TestCase):
    """Validate Figma OAuth state parameter generation and verification."""

    def test_state_is_cryptographically_random(self):
        """State values must be unique and sufficiently random."""
        from zenith.integrations.figma.oauth import generate_auth_url

        with patch("zenith.integrations.figma.oauth.settings") as mock_settings:
            mock_settings.figma_client_id = "test_client_id"
            mock_settings.figma_redirect_uri = "http://localhost:8005/api/integrations/figma/callback"

            states = set()
            for _ in range(50):
                url, state = generate_auth_url()
                self.assertIsInstance(state, str)
                self.assertGreater(len(state), 16, "State must be at least 16 chars")
                states.add(state)

            # All states should be unique
            self.assertEqual(len(states), 50, "All 50 states must be unique")

    def test_auth_url_contains_required_params(self):
        """Authorization URL must contain client_id, redirect_uri, state, scope."""
        from zenith.integrations.figma.oauth import generate_auth_url

        with patch("zenith.integrations.figma.oauth.settings") as mock_settings:
            mock_settings.figma_client_id = "test_id_123"
            mock_settings.figma_redirect_uri = "http://localhost:8005/callback"

            url, state = generate_auth_url()

            self.assertIn("client_id=test_id_123", url)
            self.assertIn("redirect_uri=", url)
            self.assertIn(f"state={state}", url)
            self.assertIn("scope=", url)
            self.assertIn("response_type=code", url)

    def test_auth_url_uses_official_figma_endpoint(self):
        """Must use www.figma.com as the OAuth endpoint."""
        from zenith.integrations.figma.oauth import generate_auth_url

        with patch("zenith.integrations.figma.oauth.settings") as mock_settings:
            mock_settings.figma_client_id = "test"
            mock_settings.figma_redirect_uri = "http://localhost:8005/callback"

            url, _ = generate_auth_url()
            self.assertTrue(
                url.startswith("https://www.figma.com/oauth"),
                f"Expected Figma OAuth URL, got: {url[:60]}"
            )


class TestCanvaOAuthPKCE(unittest.TestCase):
    """Validate Canva PKCE flow implementation."""

    def test_code_verifier_meets_spec(self):
        """Code verifier must be 43-128 chars, URL-safe."""
        from zenith.integrations.canva.oauth import generate_auth_url

        with patch("zenith.integrations.canva.oauth.settings") as mock_settings:
            mock_settings.canva_client_id = "test_canva_id"
            mock_settings.canva_redirect_uri = "http://localhost:8005/api/integrations/canva/callback"

            url, state, code_verifier = generate_auth_url()

            self.assertGreaterEqual(len(code_verifier), 43)
            self.assertLessEqual(len(code_verifier), 128)
            # RFC 7636: only unreserved chars
            import re
            self.assertRegex(code_verifier, r"^[A-Za-z0-9_~.-]+$")

    def test_code_challenge_is_s256(self):
        """Code challenge must be SHA256(verifier), base64url-encoded."""
        from zenith.integrations.canva.oauth import generate_auth_url

        with patch("zenith.integrations.canva.oauth.settings") as mock_settings:
            mock_settings.canva_client_id = "test_canva_id"
            mock_settings.canva_redirect_uri = "http://localhost:8005/callback"

            url, state, code_verifier = generate_auth_url()

            # Manually compute S256 challenge
            digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
            expected_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

            self.assertIn(f"code_challenge={expected_challenge}", url)
            self.assertIn("code_challenge_method=S256", url)

    def test_canva_auth_url_uses_official_endpoint(self):
        """Must use canva.com as the OAuth endpoint."""
        from zenith.integrations.canva.oauth import generate_auth_url

        with patch("zenith.integrations.canva.oauth.settings") as mock_settings:
            mock_settings.canva_client_id = "test"
            mock_settings.canva_redirect_uri = "http://localhost:8005/callback"

            url, _, _ = generate_auth_url()
            self.assertTrue(
                "canva.com" in url,
                f"Expected Canva OAuth URL, got: {url[:60]}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Token Lifecycle Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenSecurity(unittest.TestCase):
    """Validate token encryption and lifecycle management."""

    def test_fernet_encryption_roundtrip(self):
        """Tokens encrypted with Fernet must decrypt to original value."""
        from zenith.integrations.security import encrypt_token, decrypt_token

        test_token = "ya29.some-access-token-value"
        encrypted = encrypt_token(test_token)

        # Encrypted value must not be the plaintext
        self.assertNotEqual(encrypted, test_token)

        # Decrypted must match
        decrypted = decrypt_token(encrypted)
        self.assertEqual(decrypted, test_token)

    def test_different_tokens_produce_different_ciphertexts(self):
        """Each encryption call should produce unique ciphertext (Fernet uses IV)."""
        from zenith.integrations.security import encrypt_token

        token = "test_token_value"
        c1 = encrypt_token(token)
        c2 = encrypt_token(token)

        # Fernet uses random IV, so same plaintext → different ciphertext
        self.assertNotEqual(c1, c2)

    def test_empty_token_handling(self):
        """Empty tokens should be handled gracefully."""
        from zenith.integrations.security import encrypt_token, decrypt_token

        encrypted = encrypt_token("")
        self.assertEqual(decrypt_token(encrypted), "")


class TestIntegrationDB(unittest.TestCase):
    """Validate IntegrationDB CRUD operations with real SQLite."""

    def setUp(self):
        """Create a temp DB with the integration tables."""
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.tmp.name)
        self.tmp.close()

        # Create the tables
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS oauth_integrations (
                user_id TEXT NOT NULL DEFAULT 'local',
                provider TEXT NOT NULL,
                access_token_enc TEXT NOT NULL,
                refresh_token_enc TEXT DEFAULT '',
                token_expires_at TEXT DEFAULT '',
                scopes TEXT DEFAULT '',
                provider_user_id TEXT DEFAULT '',
                provider_user_name TEXT DEFAULT '',
                status TEXT DEFAULT 'connected',
                connected_at TEXT DEFAULT '',
                last_sync_at TEXT DEFAULT '',
                metadata_json TEXT DEFAULT '{}',
                PRIMARY KEY (user_id, provider)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT DEFAULT ''
            )
        """)
        conn.commit()
        conn.close()

        from zenith.integrations.models import IntegrationDB
        self.db = IntegrationDB(self.db_path)

    def tearDown(self):
        os.unlink(self.db_path)

    def test_upsert_and_get_connection(self):
        """Can store and retrieve an integration connection."""
        self.db.upsert_connection(
            provider="figma",
            access_token="access_123",
            refresh_token="refresh_456",
            scopes="file_content:read",
            provider_user_name="TestUser",
        )

        conn = self.db.get_connection("figma")
        self.assertIsNotNone(conn)
        self.assertEqual(conn["provider"], "figma")
        self.assertEqual(conn["access_token"], "access_123")
        self.assertEqual(conn["refresh_token"], "refresh_456")
        self.assertEqual(conn["provider_user_name"], "TestUser")

    def test_status_does_not_leak_tokens(self):
        """get_connection_status must NOT include decrypted tokens."""
        self.db.upsert_connection(
            provider="canva",
            access_token="secret_access",
            refresh_token="secret_refresh",
            scopes="design:content:read",
        )

        status = self.db.get_connection_status("canva")
        self.assertEqual(status["status"], "connected")
        # Must NOT contain token fields
        self.assertNotIn("access_token", status)
        self.assertNotIn("refresh_token", status)
        self.assertNotIn("access_token_enc", status)
        self.assertNotIn("refresh_token_enc", status)

    def test_delete_connection(self):
        """Deleting a connection removes it from the DB."""
        self.db.upsert_connection(
            provider="figma", access_token="a", refresh_token="b",
        )
        self.assertTrue(self.db.delete_connection("figma"))
        self.assertIsNone(self.db.get_connection("figma"))

    def test_expired_token_status(self):
        """Expired tokens should report status=expired."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        self.db.upsert_connection(
            provider="figma", access_token="a",
            token_expires_at=past,
        )

        status = self.db.get_connection_status("figma")
        self.assertEqual(status["status"], "expired")

    def test_list_connections(self):
        """List should return status for both providers."""
        conns = self.db.list_connections()
        self.assertEqual(len(conns), 2)
        providers = {c["provider"] for c in conns}
        self.assertEqual(providers, {"figma", "canva"})


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Design Tool Schema Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDesignToolSchemas(unittest.TestCase):
    """Validate AI tool schemas for design operations."""

    def test_all_tools_have_required_fields(self):
        """Every registered tool must have name, description, parameters, handler."""
        # Import triggers registration
        import zenith.tools.design_tools  # noqa: F401
        from zenith.core.tools import TOOLS

        design_tool_names = [
            "design_integration_status",
            "figma_get_user",
            "figma_read_file",
            "figma_inspect_nodes",
            "figma_export_assets",
            "figma_read_comments",
            "canva_get_profile",
            "canva_list_designs",
            "canva_create_design",
            "canva_export_design",
        ]

        for name in design_tool_names:
            self.assertIn(name, TOOLS, f"Tool '{name}' not registered")
            tool = TOOLS[name]
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            self.assertIn("handler", tool)
            self.assertIsNotNone(tool["handler"])

    def test_tool_parameters_are_valid_json_schema(self):
        """Tool parameters must follow JSON Schema structure."""
        import zenith.tools.design_tools  # noqa: F401
        from zenith.core.tools import TOOLS

        for name, tool in TOOLS.items():
            if not name.startswith(("figma_", "canva_", "design_")):
                continue
            params = tool["parameters"]
            self.assertEqual(params.get("type"), "object", f"{name}: params must be type=object")
            self.assertIn("properties", params, f"{name}: must have properties")
            self.assertIsInstance(params["properties"], dict)

    def test_plugin_command_types_defined(self):
        """Plugin bridge command types must be properly defined."""
        from zenith.tools.design_schemas import PLUGIN_COMMAND_TYPES

        self.assertIn("create_frame", PLUGIN_COMMAND_TYPES)
        self.assertIn("create_text", PLUGIN_COMMAND_TYPES)
        self.assertIn("create_rectangle", PLUGIN_COMMAND_TYPES)
        self.assertIn("modify_node", PLUGIN_COMMAND_TYPES)
        self.assertIn("rename_node", PLUGIN_COMMAND_TYPES)

        for cmd_type, spec in PLUGIN_COMMAND_TYPES.items():
            self.assertIn("description", spec, f"{cmd_type}: missing description")
            self.assertIn("params", spec, f"{cmd_type}: missing params")


class TestDesignToolRegistry(unittest.TestCase):
    """Validate the design tool registry."""

    def test_registry_completeness(self):
        """Registry should describe capabilities and limitations."""
        from zenith.tools.design_schemas import DESIGN_TOOL_REGISTRY

        self.assertIsInstance(DESIGN_TOOL_REGISTRY, dict)
        self.assertIn("figma", DESIGN_TOOL_REGISTRY)
        self.assertIn("canva", DESIGN_TOOL_REGISTRY)

        for provider, info in DESIGN_TOOL_REGISTRY.items():
            self.assertIn("name", info)
            self.assertIn("capabilities", info)
            self.assertIsInstance(info["capabilities"], dict)
            self.assertGreater(len(info["capabilities"]), 0)
            self.assertIn("limitations", info)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Plugin Bridge Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPluginBridge(unittest.TestCase):
    """Test the Figma plugin bridge command validation."""

    def _run(self, coro):
        """Helper to run async code in sync tests."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_unknown_command_rejected(self):
        """Unknown command types must be rejected."""
        from zenith.integrations.plugin_bridge import execute_command
        result = self._run(execute_command("nonexistent_command", {}))
        self.assertFalse(result["ok"])
        self.assertIn("Unknown command type", result["error"])

    def test_missing_required_params_rejected(self):
        """Commands with missing required params must be rejected."""
        from zenith.integrations.plugin_bridge import execute_command
        result = self._run(execute_command("create_frame", {}))
        self.assertFalse(result["ok"])
        self.assertIn("Missing required", result["error"])

    def test_no_connection_returns_error(self):
        """Commands fail gracefully when no plugin is connected."""
        from zenith.integrations.plugin_bridge import execute_command
        result = self._run(
            execute_command("create_frame", {"name": "Test", "width": 100, "height": 100})
        )
        self.assertFalse(result["ok"])
        self.assertIn("No Figma plugin connected", result["error"])

    def test_landing_page_actions_defined(self):
        """The vertical slice landing page flow must be fully defined."""
        from zenith.integrations.plugin_bridge import LANDING_PAGE_ACTIONS

        self.assertIsInstance(LANDING_PAGE_ACTIONS, list)
        self.assertGreaterEqual(len(LANDING_PAGE_ACTIONS), 4)

        # Must include frame, headline, subtitle, CTA
        types = [a["command_type"] for a in LANDING_PAGE_ACTIONS]
        self.assertIn("create_frame", types)
        self.assertIn("create_rectangle", types)
        text_count = types.count("create_text")
        self.assertGreaterEqual(text_count, 2, "Must have headline + subtitle text")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Design Concepts Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDesignConcepts(unittest.TestCase):
    """Validate design concepts are properly defined."""

    def test_design_concepts_complete(self):
        """Core design concepts must be defined."""
        from zenith.tools.design_schemas import DESIGN_CONCEPTS

        required_concepts = [
            "frames", "typography", "colors", "layout",
            "spacing", "hierarchy", "responsive",
        ]
        for concept in required_concepts:
            self.assertIn(concept, DESIGN_CONCEPTS, f"Missing concept: {concept}")
            self.assertIsInstance(DESIGN_CONCEPTS[concept], str)
            self.assertGreater(len(DESIGN_CONCEPTS[concept]), 10)


if __name__ == "__main__":
    unittest.main()
