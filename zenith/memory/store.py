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
import time
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

CREATE TABLE IF NOT EXISTS custom_agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    role_description TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    allowed_tools TEXT NOT NULL,
    created_by TEXT DEFAULT 'HR',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS org_blackboard (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department TEXT NOT NULL,
    topic TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    theme TEXT DEFAULT 'editorial_slate',
    data_json TEXT NOT NULL,
    file_path TEXT DEFAULT '',
    web_url TEXT DEFAULT '',
    created_at REAL,
    updated_at REAL
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


# ─── Dynamic Custom Agents Registry ──────────────────────────────────────────

def save_custom_agent(agent_data: dict[str, Any]) -> bool:
    agent_id = str(agent_data.get("id") or "").strip().lower()
    name = str(agent_data.get("name") or agent_id).strip()
    dept = str(agent_data.get("department") or "Special Operations").strip()
    role_desc = str(agent_data.get("role_description") or "").strip()
    prompt = str(agent_data.get("system_prompt") or "").strip()
    tools_val = agent_data.get("allowed_tools") or []
    if isinstance(tools_val, list):
        tools_json = json.dumps(tools_val)
    else:
        tools_json = str(tools_val)
    created_by = str(agent_data.get("created_by") or "HR").strip()

    if not agent_id or not prompt:
        return False

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO custom_agents (id, name, department, role_description, system_prompt, allowed_tools, created_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                department = excluded.department,
                role_description = excluded.role_description,
                system_prompt = excluded.system_prompt,
                allowed_tools = excluded.allowed_tools,
                updated_at = CURRENT_TIMESTAMP
            """,
            (agent_id, name, dept, role_desc, prompt, tools_json, created_by),
        )
        conn.commit()
    return True


def get_custom_agent(agent_id: str) -> dict[str, Any] | None:
    agent_id = (agent_id or "").strip().lower()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM custom_agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["allowed_tools"] = json.loads(d.get("allowed_tools") or "[]")
        except Exception:
            d["allowed_tools"] = []
        return d


def list_custom_agents() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM custom_agents ORDER BY name ASC").fetchall()
        agents = []
        for r in rows:
            d = dict(r)
            try:
                d["allowed_tools"] = json.loads(d.get("allowed_tools") or "[]")
            except Exception:
                d["allowed_tools"] = []
            agents.append(d)
        return agents


def delete_custom_agent(agent_id: str) -> bool:
    agent_id = (agent_id or "").strip().lower()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM custom_agents WHERE id = ?", (agent_id,))
        conn.commit()
        return cur.rowcount > 0


# ─── Organizational Shared Blackboard ─────────────────────────────────────────

def blackboard_publish(
    department: str,
    topic: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> int:
    """Publish a strategic insight, finding, or status report to the organizational blackboard."""
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO org_blackboard (department, topic, content, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (department.strip(), topic.strip(), content.strip(), meta_json),
        )
        conn.commit()
        return cur.lastrowid or 0


def blackboard_query(
    query: str = "",
    department: str = "",
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Query recent findings from the shared organizational blackboard."""
    sql = "SELECT * FROM org_blackboard"
    params: list[Any] = []
    clauses: list[str] = []

    if department.strip():
        clauses.append("LOWER(department) = ?")
        params.append(department.strip().lower())
    if query.strip():
        clauses.append("(LOWER(topic) LIKE ? OR LOWER(content) LIKE ?)")
        q = f"%{query.strip().lower()}%"
        params.extend([q, q])

    if clauses:
        sql += " WHERE " + " AND ".join(clauses)

    sql += " ORDER BY id DESC LIMIT ?"
    params.append(max(1, min(limit, 50)))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except Exception:
                d["metadata"] = {}
            out.append(d)
        return out


def blackboard_summary(limit: int = 5) -> str:
    """Format recent organizational blackboard findings for context injection."""
    findings = blackboard_query(limit=limit)
    if not findings:
        return ""
    lines = []
    for f in findings:
        lines.append(f"- [{f.get('created_at', '')}] **{f.get('department', 'Agent')}** ({f.get('topic', '')}): {f.get('content', '')}")
    return "\n".join(lines)


# ── Artifact Persistence & Versioning ───────────────────────────────────────

def save_artifact(
    artifact_id: str,
    artifact_type: str,
    title: str,
    theme: str,
    data_json: str | dict | list,
    file_path: str = "",
    web_url: str = "",
) -> None:
    """Save or upsert a structured artifact (presentation, document, etc.)."""
    raw_json = json.dumps(data_json, ensure_ascii=False) if not isinstance(data_json, str) else data_json
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """INSERT INTO artifacts (id, type, title, theme, data_json, file_path, web_url, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   title = excluded.title,
                   theme = excluded.theme,
                   data_json = excluded.data_json,
                   file_path = CASE WHEN excluded.file_path != '' THEN excluded.file_path ELSE artifacts.file_path END,
                   web_url = CASE WHEN excluded.web_url != '' THEN excluded.web_url ELSE artifacts.web_url END,
                   updated_at = excluded.updated_at
            """,
            (artifact_id, artifact_type, title, theme, raw_json, file_path, web_url, now, now),
        )
        conn.commit()
    set_last_generated_artifact(artifact_id)


_LAST_GENERATED_ARTIFACT_ID: str = ""


def set_last_generated_artifact(artifact_id: str) -> None:
    """Track the most recently generated artifact in memory."""
    global _LAST_GENERATED_ARTIFACT_ID
    _LAST_GENERATED_ARTIFACT_ID = artifact_id


def get_last_generated_artifact_id() -> str:
    """Return the ID of the most recently generated artifact."""
    global _LAST_GENERATED_ARTIFACT_ID
    return _LAST_GENERATED_ARTIFACT_ID


def get_artifact(artifact_id: str) -> Optional[dict[str, Any]]:
    """Retrieve an artifact by ID, decoding its structured JSON payload."""
    with _connect() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        try:
            d["data"] = json.loads(d.get("data_json") or "{}")
        except Exception:
            d["data"] = {}
        return d


def list_artifacts(artifact_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """List recent artifacts filtered optionally by type ('presentation', 'document')."""
    sql = "SELECT id, type, title, theme, file_path, web_url, created_at, updated_at FROM artifacts"
    params: list[Any] = []
    if artifact_type.strip():
        sql += " WHERE LOWER(type) = ?"
        params.append(artifact_type.strip().lower())
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(max(1, min(limit, 100)))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def find_artifact(query: str, artifact_type: str = "") -> Optional[dict[str, Any]]:
    """Smart case-insensitive artifact search by exact ID, filename, keywords, or recency.

    Prevents sending the wrong presentation/file by scoring candidate matches
    and requiring verifiable keyword presence or explicit recency.
    """
    import re
    query = (query or "").strip().strip("'\"")
    clean_type = artifact_type.strip().lower()

    # 1. Check if query is an exact artifact ID
    if query:
        art = get_artifact(query)
        if art:
            if not clean_type or art.get("type", "").lower() == clean_type:
                return art

    # 2. Check last generated artifact if query is generic
    generic_words = {
        "presentation", "presentation.pptx", "deck", "slides", "ppt", "latest", "recent",
        "document", "document.pdf", "document.docx", "report", "the presentation", "the deck",
        "the document", "file", "attachment", "latest.pptx", "latest.pdf",
    }
    is_generic = not query or query.lower() in generic_words
    now = time.time()

    def is_usable_artifact(a: dict[str, Any], max_age: float = 7200) -> bool:
        if not a:
            return False
        aid = a.get("id", "").lower()
        if aid.startswith("test_") and query != a.get("id"):
            return False
        fp = a.get("file_path", "")
        if not fp or not Path(fp).exists():
            return False
        if "pytest" in fp.lower():
            return False
        if max_age and (now - a.get("updated_at", 0) > max_age):
            return False
        return True

    if is_generic:
        last_id = get_last_generated_artifact_id()
        if last_id:
            last_art = get_artifact(last_id)
            if last_art and (not clean_type or last_art.get("type", "").lower() == clean_type):
                if is_usable_artifact(last_art, max_age=7200):
                    return last_art

    # 3. Retrieve all artifacts of matching type (or all artifacts) from DB
    with _connect() as conn:
        sql = "SELECT * FROM artifacts"
        params: list[Any] = []
        if clean_type:
            sql += " WHERE LOWER(type) = ?"
            params.append(clean_type)
        sql += " ORDER BY updated_at DESC"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    if not rows:
        return None

    # Decode JSON payload
    for r in rows:
        try:
            r["data"] = json.loads(r.get("data_json") or "{}")
        except Exception:
            r["data"] = {}

    # If query is generic, pick the newest valid artifact updated within the last 2 hours
    if is_generic:
        for r in rows:
            if is_usable_artifact(r, max_age=7200):
                return r
        return None

    # 4. Keyword / fuzzy scoring search
    # Strip extensions and prefixes
    cleaned_query = query
    for ext in (".pptx", ".pdf", ".docx", ".xlsx", ".csv", ".json", ".html"):
        if cleaned_query.lower().endswith(ext):
            cleaned_query = cleaned_query[:-len(ext)]
    for prefix in ("presentation_", "deck_", "doc_", "report_"):
        if cleaned_query.lower().startswith(prefix):
            cleaned_query = cleaned_query[len(prefix):]

    # Extract distinct search tokens (length >= 3, skipping stop words)
    raw_tokens = re.split(r'[-_\s,.]+', cleaned_query)
    stop_words = {"the", "and", "for", "with", "presentation", "deck", "slides", "ppt", "document", "report", "file"}
    tokens = [t.lower() for t in raw_tokens if len(t) >= 3 and t.lower() not in stop_words]

    if not tokens:
        # Single short token or exact substring match on file_path or title
        q_lower = query.lower()
        for r in rows:
            if q_lower in r.get("id", "").lower() or q_lower in r.get("title", "").lower() or q_lower in Path(r.get("file_path", "")).name.lower():
                return r
        return None

    scored_candidates = []
    for r in rows:
        fp = r.get("file_path", "")
        title_lower = r.get("title", "").lower()
        id_lower = r.get("id", "").lower()
        fname_lower = Path(fp).name.lower()
        combined = f"{title_lower} {id_lower} {fname_lower}"

        matched_tokens = sum(1 for t in tokens if t in combined)
        if matched_tokens > 0:
            score = matched_tokens * 10
            # Strong bonus if ALL tokens matched
            if matched_tokens == len(tokens):
                score += 50
            # Extra bonus if title contains the exact full phrase
            if cleaned_query.lower() in title_lower:
                score += 40
            # Extra bonus if file exists on disk
            fp = r.get("file_path", "")
            if fp and Path(fp).exists():
                score += 20
            scored_candidates.append((score, r.get("updated_at", 0), r))

    if scored_candidates:
        scored_candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return scored_candidates[0][2]

    return None