"""Personal notes tool — the Zenith scratchpad."""
from __future__ import annotations

from ..memory.store import _connect

NOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _init() -> None:
    with _connect() as conn:
        conn.execute(NOTES_SCHEMA)
        conn.commit()


def create(title: str, text: str) -> str:
    _init()
    with _connect() as conn:
        conn.execute("INSERT INTO notes (title, text) VALUES (?, ?)", (title, text))
        conn.commit()
    return f"Note created: {title}"


def list_notes() -> str:
    _init()
    with _connect() as conn:
        rows = conn.execute("SELECT id, title FROM notes ORDER BY updated_at DESC LIMIT 30").fetchall()
    if not rows:
        return "No notes yet."
    return "\n".join(f"- [{r['id']}] {r['title']}" for r in rows)


def all_notes(limit: int = 20) -> list[dict]:
    """Raw note rows newest-first."""
    _init()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM notes ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_note(note_id: int) -> str:
    _init()
    with _connect() as conn:
        row = conn.execute("SELECT title, text FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not row:
        return "Note not found."
    return f"# {row['title']}\n{row['text']}"


def delete_note(note_id: int) -> str:
    _init()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.commit()
    return "Note deleted." if cur.rowcount else "Note not found."


async def notes(action: str, title: str = "", text: str = "") -> str:
    """Tool handler for 'notes'."""
    action = (action or "").lower()
    if action == "create":
        if not title:
            return "Please provide a title."
        return _create(title, text)
    if action == "list":
        return list_notes()
    if action == "get":
        try:
            nid = int(title)
        except ValueError:
            return "Provide a numeric note id."
        return get_note(nid)
    if action == "delete":
        try:
            nid = int(title)
        except ValueError:
            return "Provide a numeric note id."
        return delete_note(nid)
    return "Unknown notes action."


def _create(title: str, text: str) -> str:
    return create(title.strip() or "untitled", text)