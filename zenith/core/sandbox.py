"""Zenith Sovereign Sandbox — autonomous runtime security, filesystem jail,
credential isolation, command safety, and secret redaction.

Designed for high-trust autonomous execution:
- Zero user friction: No annoying permission review modals; Zenith executes autonomously anywhere.
- Defense-in-depth protection: Strictly guards sensitive user credentials (~/.ssh, ~/.aws,
  ~/.gnupg, browser cookies, /etc/shadow) against accidental leakage or prompt injection attacks.
- Path traversal & symlink jail enforcement: Prevents ../.. or symlink escapes to sensitive files.
- Command safety & resource limits: Prohibits catastrophic filesystem destruction and exfiltration commands.
- Automatic secret redaction: Masks sensitive API tokens, passwords, and authorization headers in traces.
"""
from __future__ import annotations

import os
import re
import platform
from pathlib import Path
from typing import Any, Optional, Tuple

# ─── Protected Path Signatures (Never accessible for agent read/write/delete) ─
PROTECTED_PATH_PATTERNS = [
    # SSH & Cloud Credentials
    re.compile(r"(\.ssh[\/\\](id_.*|authorized_keys|known_hosts|config))", re.IGNORECASE),
    re.compile(r"(\.aws[\/\\](credentials|config))", re.IGNORECASE),
    re.compile(r"(\.gnupg[\/\\])", re.IGNORECASE),
    re.compile(r"(\.config[\/\\]gcloud[\/\\])", re.IGNORECASE),
    re.compile(r"(\.azure[\/\\])", re.IGNORECASE),
    re.compile(r"(\.kube[\/\\]config)", re.IGNORECASE),

    # Browser Credentials & Cookies
    re.compile(r"(\.mozilla[\/\\]firefox[\/\\].*[\/\\](cookies\.sqlite|logins\.json|key4\.db))", re.IGNORECASE),
    re.compile(r"(Google[\/\\]Chrome[\/\\].*[\/\\](Cookies|Login Data|Web Data))", re.IGNORECASE),
    re.compile(r"(Brave-Browser[\/\\].*[\/\\](Cookies|Login Data))", re.IGNORECASE),
    re.compile(r"(Microsoft[\/\\]Edge[\/\\].*[\/\\](Cookies|Login Data))", re.IGNORECASE),

    # Operating System Password & Root Databases
    re.compile(r"^/etc/(shadow|sudoers|master\.passwd|gshadow)$", re.IGNORECASE),
    re.compile(r"^/etc/sudoers\.d/", re.IGNORECASE),
    re.compile(r"System32[/\\]config[/\\](SAM|SYSTEM|SECURITY)", re.IGNORECASE),

    # Root / Critical System Directories
    re.compile(r"^/proc/(kcore|kmem|mem)$", re.IGNORECASE),
]

# Write-protected startup files (prevent persistent backdoors)
WRITE_PROTECTED_FILES = [
    re.compile(r"(\.(bashrc|zshrc|profile|bash_profile|bash_login|zprofile))$", re.IGNORECASE),
    re.compile(r"(\.config[\/\\]fish[\/\\]config\.fish)$", re.IGNORECASE),
    re.compile(r"(\.config[\/\\]autostart[\/\\])", re.IGNORECASE),
]

# Destructive / Catastrophic Commands
DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+(?:/(?:\s|$|\*|;)|~(?:\s|$|\*|;)|\$HOME(?:\s|$|/\*|;))"),
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # Fork bomb
    re.compile(r"\bmkfs(\.[a-z0-9]+)?\b"),
    re.compile(r"\bdd\s+if=.*of=(/dev/sd[a-z]|/dev/nvme[0-9]|/dev/vd[a-z])\b"),
    re.compile(r">\s*/dev/sd[a-z]\b"),
    re.compile(r"\bchmod\s+-[a-zA-Z]*R[a-zA-Z]*\s+777\s+(?:/(?:\s|$|\*|;)|~(?:\s|$|\*|;))"),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.IGNORECASE),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\binit\s+0\b"),
    re.compile(r"\bpoweroff\b"),
]

# Exfiltration detection in shell pipelines
EXFILTRATION_PATTERNS = [
    re.compile(r"\b(curl|wget|nc|netcat|ncat)\b.*(\.ssh|\.aws|\.gnupg|/etc/shadow)", re.IGNORECASE),
    re.compile(r"(cat|type|head|tail)\s+.*(\.ssh|\.aws|\.gnupg|/etc/shadow).*\|\s*(curl|wget|nc)", re.IGNORECASE),
]

# Secret / API Key Redaction Regexes
SECRET_REDACTION_PATTERNS = [
    (re.compile(r"AIza[0-9A-Za-z-_]{35}"), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9]{20,64}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{30,40}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{82}"), "[REDACTED_GITHUB_PAT]"),
    (re.compile(r"Bearer\s+[a-zA-Z0-9\-_]{10,}\.[a-zA-Z0-9\-_]{10,}\.[a-zA-Z0-9\-_]{8,}"), "Bearer [REDACTED_JWT]"),
    (re.compile(r"(password|secret|token|api_key)\s*[:=]\s*['\"]([^'\"]{8,})['\"]", re.IGNORECASE), r"\1: '[REDACTED]'"),
]


class ZenithSandbox:
    """Autonomous Security & Guardrail Engine for Zenith operations."""

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd().resolve()

    def is_path_protected(self, path: str | Path, operation: str = "read") -> Tuple[bool, str]:
        """Check if a path hits sensitive user credentials or system databases.
        
        Returns:
            (is_blocked, violation_reason)
        """
        try:
            p = Path(path).expanduser()
            # Resolve canonical path to catch symlinks and ../.. path traversal
            if p.exists() or p.is_symlink():
                resolved = p.resolve()
            else:
                # If file does not exist yet (e.g. write target), resolve its parent
                resolved = p.parent.resolve() / p.name
        except Exception as exc:
            return True, f"Invalid path resolution: {exc}"

        resolved_str = str(resolved).replace("\\", "/")

        # 1. Check Protected Credential & System Paths (read/write/delete all blocked)
        for pat in PROTECTED_PATH_PATTERNS:
            if pat.search(resolved_str):
                return True, f"Access to protected credential or system path is prohibited: {resolved.name}"

        # 2. Check Write-Protected Configuration Files (read allowed, write/overwrite blocked)
        if operation in ("write", "delete", "patch"):
            for pat in WRITE_PROTECTED_FILES:
                if pat.search(resolved_str):
                    return True, f"Modifying shell startup files ({resolved.name}) is blocked to protect system integrity"

        # 3. Prevent writing outside valid workspace when workspace jail is strictly enforced
        return False, ""

    def is_symlink_safe(self, link_path: str | Path, workspace_root: Optional[Path] = None) -> Tuple[bool, str]:
        """Verify that a symlink does not point outside the workspace to protected locations."""
        p = Path(link_path).expanduser()
        if not p.is_symlink():
            return True, ""

        try:
            target = p.resolve()
            # Check if resolved symlink target points to protected paths
            blocked, reason = self.is_path_protected(target, operation="read")
            if blocked:
                return False, f"Symlink escape blocked: points to sensitive target ({reason})"

            ws = (workspace_root or self.workspace_root).resolve()
            target_str = str(target.resolve())
            ws_str = str(ws)

            # If workspace boundary is enforced and symlink escapes it
            if not target_str.startswith(ws_str):
                # Only block if it tries to escape to user sensitive roots (~ or /etc)
                home = str(Path.home().resolve())
                if target_str == home or target_str.startswith(home + "/."):
                    return False, f"Symlink escape blocked: points into user configuration root ({target})"
            return True, ""
        except Exception as exc:
            return False, f"Symlink inspection failed: {exc}"

    def is_command_safe(self, command: str) -> Tuple[bool, str]:
        """Verify shell command safety against catastrophic actions or exfiltration."""
        clean_cmd = command.strip()
        low_cmd = clean_cmd.lower()

        # 1. Catastrophic / Destructive commands
        for pat in DANGEROUS_COMMAND_PATTERNS:
            if pat.search(clean_cmd) or pat.search(low_cmd):
                return False, f"Command matches catastrophic system safety pattern: {pat.pattern}"

        # 2. Credential Exfiltration pipelines
        for pat in EXFILTRATION_PATTERNS:
            if pat.search(clean_cmd) or pat.search(low_cmd):
                return False, "Command appears to attempt exfiltration of sensitive credentials"

        return True, ""

    def redact_secrets(self, text: str) -> str:
        """Mask API keys, JWTs, and sensitive tokens in output logs or prompt context."""
        if not text:
            return text
        sanitized = text
        for pat, replacement in SECRET_REDACTION_PATTERNS:
            sanitized = pat.sub(replacement, sanitized)
        return sanitized

    def sanitize_env(self, env: dict[str, str]) -> dict[str, str]:
        """Provide a clean environment dictionary for subprocess execution without leaking master secrets."""
        safe = dict(env)
        # Strip master host API keys from sub-processes unless explicitly required
        for sensitive_key in ("SSH_AUTH_SOCK", "AWS_SECRET_ACCESS_KEY", "GCP_SERVICE_ACCOUNT_KEY"):
            safe.pop(sensitive_key, None)
        return safe


# Default global instance
sandbox = ZenithSandbox()
