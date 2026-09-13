"""SQLite-backed long-term memory + knowledge graph (Layers 7 & 11).

Two storage families:
  - long_term_memories  (category -> key -> value), a flexible fact store.
  - graph_entities / graph_edges: a lightweight knowledge graph with typed
    entities and weighted relations — Zenith's connective tissue.

SQLite is fine for a single-user assistant at this scale. The schema is
deliberately simple; a vector store can be added later without breaking callers.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from ..core.config import settings

_DB_PATH = settings.db_path
DB_PATH = str(_DB_PATH)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,
    meta TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    rel TEXT NOT NULL,
    target TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, rel, target)
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    at TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    done INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    at TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id TEXT UNIQUE NOT NULL,
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS oauth_integrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'local',
    provider TEXT NOT NULL,
    access_token_enc TEXT,
    refresh_token_enc TEXT,
    token_expires_at TIMESTAMP,
    scopes TEXT DEFAULT '',
    provider_user_id TEXT,
    provider_user_name TEXT,
    status TEXT DEFAULT 'not_connected',
    connected_at TIMESTAMP,
    last_sync_at TIMESTAMP,
    metadata_json TEXT DEFAULT '{}',
    UNIQUE(user_id, provider)
);

CREATE TABLE IF NOT EXISTS oauth_states (
    state TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT 'local',
    pkce_verifier_enc TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS integration_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL DEFAULT 'local',
    provider TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
        # Existing DBs may have accumulated duplicate (source, rel, target)
        # rows before the UNIQUE constraint existed — collapse them, keeping
        # the max weight per triplet, and ensure unique index exists.
        conn.execute(
            """DELETE FROM relations WHERE id NOT IN (
                 SELECT MAX(id) FROM relations GROUP BY source, rel, target
               )"""
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_relations_triplet ON relations(source, rel, target)"
        )
        conn.commit()
    _seed_defaults()


def _seed_defaults() -> None:
    """Seed a handful of starter facts so the assistant isn't a blank slate."""
    seed = [
        ("projects", "zenith", "Zenith — Autonomous AI companion & homelab control plane."),
        ("user", "name", settings.user_name or "Friend"),
        ("user", "role", "Developer / Explorer"),
    ]
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO memories (category, key, value) VALUES (?, ?, ?)",
            [(c, k, v) for c, k, v in seed],
        )
        conn.commit()


# ─── Memories (fact store) ─────────────────────────────────────────────────────

def save_memory(category: str, key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO memories (category, key, value)
               VALUES (?, ?, ?)
               ON CONFLICT(category, key) DO UPDATE SET value=excluded.value, updated_at=CURRENT_TIMESTAMP""",
            (category, key, value),
        )
        conn.commit()


def recall_memory(query: str, limit: int = 10) -> list[dict[str, str]]:
    """Fuzzy-text recall across memory keys and values."""
    q = f"%{query}%"
    with _connect() as conn:
        rows = conn.execute(
            """SELECT category, key, value FROM memories
               WHERE key LIKE ? OR value LIKE ? OR category LIKE ?
               ORDER BY updated_at DESC LIMIT ?""",
            (q, q, q, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def all_memories() -> list[dict[str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT category, key, value FROM memories ORDER BY category, key"
        ).fetchall()
    return [dict(r) for r in rows]


def memory_summary(limit: int = 60) -> str:
    # Bounded frontier: the FULL memories table can grow to 20KB+ and is injected
    # into every system prompt. Show the most recently-relevant facts instead —
    # favorites/critical categories first, then the newest edits.
    with _connect() as conn:
        rows = conn.execute(
            """SELECT category, key, value, updated_at FROM memories
               ORDER BY CASE WHEN category IN ('favorites', 'preferences', 'user') THEN 0 ELSE 1 END,
                        updated_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    if not rows:
        return "No long-term memories stored yet."
    lines = [f"[{r['category'].upper()}] {r['key']}: {r['value']}" for r in rows]
    return "\n".join(lines)


def delete_memory(key: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE key = ?", (key,))
        conn.commit()
    return cur.rowcount > 0


# ─── Knowledge Graph ──────────────────────────────────────────────────────────

def add_entity(name: str, entity_type: str, meta: dict | None = None) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO entities (name, type, meta) VALUES (?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET type=excluded.type, meta=excluded.meta""",
            (name, entity_type, json.dumps(meta or {})),
        )
        conn.commit()


def add_relation(source: str, rel: str, target: str, weight: float = 1.0) -> None:
    with _connect() as conn:
        # Dedupe: repeated extractions were piling up exact (source, rel, target)
        # triplets (e.g. repeated extractions of relations). Upsert keeps
        # the strongest weight and newest timestamp.
        conn.execute(
            """INSERT INTO relations (source, rel, target, weight) VALUES (?, ?, ?, ?)
               ON CONFLICT(source, rel, target) DO UPDATE SET weight = MAX(weight, excluded.weight)""",
            (source, rel, target, weight),
        )
        conn.commit()
    # Ensure both endpoints exist as entities.
    add_entity(source, "entity")
    add_entity(target, "entity")


def query_graph(term: str) -> list[dict[str, Any]]:
    q = f"%{term}%"
    with _connect() as conn:
        rows = conn.execute(
            """SELECT source, rel, target, weight FROM relations
               WHERE source LIKE ? OR target LIKE ? OR rel LIKE ?
               ORDER BY weight DESC LIMIT 50""",
            (q, q, q),
        ).fetchall()
    return [dict(r) for r in rows]


def graph_export() -> dict[str, Any]:
    """Full graph for UI visualization."""
    with _connect() as conn:
        nodes = [dict(r) for r in conn.execute("SELECT name, type FROM entities").fetchall()]
        edges = [dict(r) for r in conn.execute("SELECT source, rel, target FROM relations").fetchall()]
    return {"nodes": nodes, "edges": edges}


def graph_stats() -> dict[str, int]:
    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS c FROM entities").fetchone()["c"]
        e = conn.execute("SELECT COUNT(*) AS c FROM relations").fetchone()["c"]
    return {"entities": n, "edges": e}


# ─── Conversations (shadow log) ───────────────────────────────────────────────

def log_conversation(role: str, content: str) -> None:
    if not content.strip():
        return
    with _connect() as conn:
        conn.execute("INSERT INTO conversations (role, content) VALUES (?, ?)", (role, content))
        conn.commit()


def recent_conversation(limit: int = 20) -> list[dict[str, str]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT role, content, timestamp FROM conversations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))


# ─── Semantic (vector) memory — stub for later ────────────────────────────────

def semantic_search(query: str, limit: int = 5) -> list[dict[str, str]]:
    """Placeholder for vector memory. Falls back to recall_memory.

    When a vector store is added, replace this with an embedding lookup.
    """
    return recall_memory(query, limit)


# Convenience alias matching the tools contract.
def memory_summary_for_prompt() -> str:
    return memory_summary()


# ─── Processed Emails Tracker ──────────────────────────────────────────────────

def is_email_processed(msg_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT id FROM processed_emails WHERE msg_id = ?", (msg_id,)).fetchone()
        return row is not None


def mark_email_processed(msg_id: str, sender: str, subject: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO processed_emails (msg_id, sender, subject) VALUES (?, ?, ?)",
            (msg_id, sender, subject),
        )
        conn.commit()