"""To-do list tool."""
from __future__ import annotations

from ..memory.store import _connect


def add(title: str) -> str:
    with _connect() as conn:
        conn.execute("INSERT INTO todos (title) VALUES (?)", (title,))
        conn.commit()
    return f"Added todo: {title}"


def list_todos() -> str:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, done FROM todos ORDER BY done ASC, id DESC LIMIT 50"
        ).fetchall()
    if not rows:
        return "No todos."
    lines = []
    for r in rows:
        mark = "✓" if r["done"] else "•"
        lines.append(f"{mark} [{r['id']}] {r['title']}")
    return "\n".join(lines)


def all_todos(limit: int = 50) -> list[dict]:
    """Raw todo rows newest-first (UI + scheduler-friendly)."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, done FROM todos ORDER BY done ASC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def open_todos() -> list[dict]:
    """Open (not-done) todos for nudges."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, done FROM todos WHERE done = 0 ORDER BY id DESC LIMIT 30"
        ).fetchall()
    return [dict(r) for r in rows]


def done(todo_id: int) -> str:
    with _connect() as conn:
        cur = conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
        conn.commit()
    return "Marked done." if cur.rowcount else "Todo not found."


def delete(todo_id: int) -> str:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        conn.commit()
    return "Deleted." if cur.rowcount else "Todo not found."


async def todo(action: str, title: str = "", todo_id: int | None = None) -> str:
    action = (action or "").lower()
    if action == "add":
        if not title:
            return "Provide a todo title."
        return add(title)
    if action == "list":
        return list_todos()
    if action == "done":
        if todo_id is None:
            return "Provide todo_id."
        return done(todo_id)
    if action == "delete":
        if todo_id is None:
            return "Provide todo_id."
        return delete(todo_id)
    return "Unknown todo action."