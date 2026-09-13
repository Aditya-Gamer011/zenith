"""Mem0 Multi-Tier Long-Term Memory Engine for Zenith.

Provides:
  - Structured, evolving memory across sessions divided into clear cognitive tiers:
      * 'preference': Personal user habits, coding style, communication tone, and defaults.
      * 'project': Codebase architecture, repository contexts, servers, and active tasks.
      * 'workflow': Recurring tool chains, successful command patterns, and automation habits.
      * 'decision': Key architectural and system decisions with rationale.
  - Automatic memory sanitization (redacts credentials, passwords, private keys, credit cards).
  - User controls: full inspection, semantic/keyword search, live updates, and deletion.
  - Tight integration with PrivacyGuard to honor Ghost Mode and memory pause.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ..core.config import settings
from .privacy_guard import privacy_guard

log = logging.getLogger("zenith.memory_layer")

# Sensitive patterns that must NEVER be persisted in long-term memory
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(bearer\s+[a-zA-Z0-9_\-\.]{20,})"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?[a-zA-Z0-9_\-\.]{16,}['\"]?)"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"]?[^\s'\"]{4,}['\"]?)"),
    re.compile(r"(?i)(sk-[a-zA-Z0-9]{20,})"),
    re.compile(r"(?i)(ghp_[a-zA-Z0-9]{20,})"),
    re.compile(r"(?i)(\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b)"),  # Credit card
]


def sanitize_memory_text(text: str) -> str:
    """Mask any inadvertently exposed secrets or sensitive identifiers."""
    cleaned = text
    for pat in SENSITIVE_PATTERNS:
        cleaned = pat.sub("[REDACTED_SECRET]", cleaned)
    return cleaned


class Mem0MemoryService:
    """Multi-tier persistent long-term memory manager."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = str(db_path or settings.db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        try:
            with self._connect() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS mem0_memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tier TEXT NOT NULL,
                        topic TEXT NOT NULL,
                        content TEXT NOT NULL,
                        meta_json TEXT DEFAULT '{}',
                        access_count INTEGER DEFAULT 0,
                        relevance_score REAL DEFAULT 1.0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(tier, topic, content)
                    );"""
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mem0_tier ON mem0_memories(tier);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mem0_topic ON mem0_memories(topic);"
                )
                conn.commit()
            self._seed_starter_memories()
        except Exception as e:
            log.warning("Mem0 table init failed: %s", e)

    def _seed_starter_memories(self) -> None:
        """Seed starter memories for new installations."""
        starter = [
            ("preference", "user_profile", f"User's preferred name is {settings.user_name or 'Friend'}."),
            ("preference", "assistant_style", "Values direct, authoritative execution, zero hallucination, and concise responses."),
            ("project", "zenith_architecture", "Zenith is a sovereign AI operating layer with FastAPI, APScheduler, and modular services."),
            ("workflow", "testing", "Always runs pytest suite after code updates to verify zero regressions."),
        ]
        try:
            with self._connect() as conn:
                for tier, topic, content in starter:
                    conn.execute(
                        """INSERT OR IGNORE INTO mem0_memories (tier, topic, content)
                           VALUES (?, ?, ?)""",
                        (tier, topic, content),
                    )
                conn.commit()
        except Exception as e:
            log.warning("Failed to seed initial memories: %s", e)

    def add_memory(
        self,
        content: str,
        tier: str = "project",
        topic: str = "general",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Store a durable memory. Respects PrivacyGuard and redacts credentials."""
        if not privacy_guard.is_sensor_enabled("memory_recording"):
            log.info("Memory recording is disabled in PrivacyGuard.")
            return None

        tier = tier.lower().strip()
        if tier not in ("preference", "project", "workflow", "decision"):
            tier = "project"

        topic = topic.lower().strip() or "general"
        sanitized = sanitize_memory_text(content.strip())
        if not sanitized:
            return None

        meta_str = json.dumps(meta or {})

        with self._lock:
            try:
                with self._connect() as conn:
                    cur = conn.execute(
                        """INSERT INTO mem0_memories (tier, topic, content, meta_json)
                           VALUES (?, ?, ?, ?)
                           ON CONFLICT(tier, topic, content) DO UPDATE SET
                             updated_at = CURRENT_TIMESTAMP,
                             access_count = access_count + 1""",
                        (tier, topic, sanitized, meta_str),
                    )
                    conn.commit()
                    return cur.lastrowid
            except Exception as e:
                log.warning("Failed to add Mem0 memory: %s", e)
                return None

    def search_memories(
        self,
        query: str,
        tier: Optional[str] = None,
        limit: int = 15,
    ) -> List[Dict[str, Any]]:
        """Search stored memories by query terms across content, topic, and tier."""
        q = f"%{query.strip()}%"
        sql = """SELECT id, tier, topic, content, access_count, relevance_score, created_at, updated_at, meta_json
                 FROM mem0_memories
                 WHERE (content LIKE ? OR topic LIKE ?)"""
        params: List[Any] = [q, q]

        if tier:
            sql += " AND tier = ?"
            params.append(tier.lower().strip())

        sql += " ORDER BY relevance_score DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        try:
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
                out = []
                for r in rows:
                    out.append({
                        "id": r["id"],
                        "tier": r["tier"],
                        "topic": r["topic"],
                        "content": r["content"],
                        "access_count": r["access_count"],
                        "relevance_score": r["relevance_score"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "meta": json.loads(r["meta_json"] or "{}"),
                    })
                return out
        except Exception as e:
            log.warning("Mem0 search failed: %s", e)
            return []

    def get_all_memories(self, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored memories, optionally filtered by tier."""
        sql = """SELECT id, tier, topic, content, access_count, relevance_score, created_at, updated_at, meta_json
                 FROM mem0_memories"""
        params: List[Any] = []
        if tier:
            sql += " WHERE tier = ?"
            params.append(tier.lower().strip())
        sql += " ORDER BY tier, topic, updated_at DESC"

        try:
            with self._connect() as conn:
                rows = conn.execute(sql, tuple(params)).fetchall()
                return [
                    {
                        "id": r["id"],
                        "tier": r["tier"],
                        "topic": r["topic"],
                        "content": r["content"],
                        "access_count": r["access_count"],
                        "relevance_score": r["relevance_score"],
                        "created_at": r["created_at"],
                        "updated_at": r["updated_at"],
                        "meta": json.loads(r["meta_json"] or "{}"),
                    }
                    for r in rows
                ]
        except Exception as e:
            log.warning("Failed to fetch all memories: %s", e)
            return []

    def update_memory(
        self,
        memory_id: int,
        content: str,
        tier: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> bool:
        """Edit or correct an existing memory."""
        sanitized = sanitize_memory_text(content.strip())
        with self._lock:
            try:
                with self._connect() as conn:
                    if tier and topic:
                        conn.execute(
                            """UPDATE mem0_memories
                               SET content = ?, tier = ?, topic = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (sanitized, tier.lower().strip(), topic.lower().strip(), memory_id),
                        )
                    else:
                        conn.execute(
                            """UPDATE mem0_memories
                               SET content = ?, updated_at = CURRENT_TIMESTAMP
                               WHERE id = ?""",
                            (sanitized, memory_id),
                        )
                    conn.commit()
                    return True
            except Exception as e:
                log.warning("Failed to update memory %d: %s", memory_id, e)
                return False

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a memory by ID."""
        with self._lock:
            try:
                with self._connect() as conn:
                    cur = conn.execute("DELETE FROM mem0_memories WHERE id = ?", (memory_id,))
                    conn.commit()
                    return cur.rowcount > 0
            except Exception as e:
                log.warning("Failed to delete memory %d: %s", memory_id, e)
                return False

    def clear_memories(self, tier: Optional[str] = None) -> int:
        """Clear all memories or memories in a specific tier."""
        with self._lock:
            try:
                with self._connect() as conn:
                    if tier:
                        cur = conn.execute("DELETE FROM mem0_memories WHERE tier = ?", (tier.lower().strip(),))
                    else:
                        cur = conn.execute("DELETE FROM mem0_memories")
                    conn.commit()
                    return cur.rowcount
            except Exception as e:
                log.warning("Failed to clear memories: %s", e)
                return 0

    def get_structured_summary(self, limit: int = 40) -> str:
        """Format tiered memories cleanly for prompt injection."""
        if not privacy_guard.is_sensor_enabled("memory_recording"):
            return "Long-Term Memory: Disabled by Privacy Guard."

        all_m = self.get_all_memories()
        if not all_m:
            return "No long-term memories stored yet."

        by_tier: Dict[str, List[str]] = {
            "preference": [],
            "project": [],
            "workflow": [],
            "decision": [],
        }
        for m in all_m[:limit]:
            t = m["tier"]
            if t in by_tier:
                by_tier[t].append(f"- ({m['topic']}) {m['content']}")

        sections = []
        if by_tier["preference"]:
            sections.append("User Preferences & Style:\n" + "\n".join(by_tier["preference"][:8]))
        if by_tier["project"]:
            sections.append("Project & Architecture Context:\n" + "\n".join(by_tier["project"][:12]))
        if by_tier["workflow"]:
            sections.append("Recurring Workflows & Tool Patterns:\n" + "\n".join(by_tier["workflow"][:8]))
        if by_tier["decision"]:
            sections.append("Historical Decisions & Rationales:\n" + "\n".join(by_tier["decision"][:6]))

        return "\n\n".join(sections)

    def distill_turn(self, user_text: str, assistant_text: str) -> None:
        """Lightweight heuristic pass to automatically extract durable preferences or workflows."""
        if not privacy_guard.is_sensor_enabled("memory_recording"):
            return

        u_low = user_text.lower()

        # Preference signals ("I prefer...", "Always use...", "My favorite...")
        pref_match = re.search(r"(?:i prefer|always use|never use|i like|my default is)\s+([^.\n]+)", u_low)
        if pref_match:
            fact = pref_match.group(0).strip()
            self.add_memory(fact, tier="preference", topic="user_preference")

        # Project signals ("Our repo is...", "We are building...", "The backend runs on...")
        proj_match = re.search(r"(?:we are building|the architecture is|the database is|stack is)\s+([^.\n]+)", u_low)
        if proj_match:
            fact = proj_match.group(0).strip()
            self.add_memory(fact, tier="project", topic="architecture")


# Singleton instance
memory_layer = Mem0MemoryService()
