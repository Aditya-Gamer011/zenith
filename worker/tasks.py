"""Persistent task store for the Zenith × Antigravity worker.

A Task is a long-running, queryable unit of work:

    {
      "id": "t_<uuid8>",
      "status": QUEUED|STARTING|RUNNING|WAITING_FOR_INPUT|COMPLETED|FAILED|CANCELLED,
      "created_at": ISO,
      "started_at": ISO|None,
      "completed_at": ISO|None,
      "workspace": str,           # absolute dir the agent works in
      "spec": { ... },            # structured engineering brief (see brief.py)
      "prompt": str,              # the exact Antigravity prompt that was run
      "current_activity": str,    # best non-empty strip of latest stream-json activity
      "output": str,              # accumulated final/partial agent output text
      "errors": [str],
      "artifacts": [str],         # paths discovered in the workspace post-run
      "worker": "antigravity-agy",
      "conversation_id": str|None,# agy conversation id (for follow-up turns)
      "parent": str|None,         # Zenith conversation id (source)
    }

Persistence: an append-only JSONL file (one JSON object per task update), so a
crash loses at most the in-flight subprocess, not the task ledger. Statuses
follow the user's requested state machine.
"""
from __future__ import annotations

import json
import os
import threading
import time

from dataclasses import dataclass, field, asdict

# Statuses (user-specified)
QUEUED = "QUEUED"
STARTING = "STARTING"
RUNNING = "RUNNING"
WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
COMPLETED = "COMPLETED"
FAILED = "FAILED"
CANCELLED = "CANCELLED"

STATUSES = (QUEUED, STARTING, RUNNING, WAITING_FOR_INPUT, COMPLETED, FAILED, CANCELLED)

_DEFAULT_STORE = os.environ.get("ZENITH_WORKER_STORE", "worker/tasks.jsonl")


@dataclass
class Task:
    id: str
    status: str = QUEUED
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    workspace: str = ""
    spec: dict = field(default_factory=dict)
    prompt: str = ""
    current_activity: str = ""
    output: str = ""
    errors: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    worker: str = "antigravity-agy"
    conversation_id: str | None = None
    parent: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _now() -> str:
    # RFC3339-ish UTC
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


class TaskStore:
    """Thread-safe append-only JSONL task ledger with an in-memory index."""

    def __init__(self, path: str = _DEFAULT_STORE):
        self.path = path
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    t = Task(**obj)
                    if t.id not in self._tasks or self._recency(t, self._tasks[t.id]) >= 0:
                        self._tasks[t.id] = t
            # The append-only ledger grows without bound; collapse to the newest
            # line per task on startup so restarts don't compound it.
            self.compact()
        except OSError:
            pass

    @staticmethod
    def _recency(a: Task, b: Task) -> int:
        return (a.completed_at or a.created_at).__gt__(b.completed_at or b.created_at)

    def _append(self, t: Task) -> None:
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")

    def create(self, spec: dict, workspace: str, prompt: str = "", parent: str | None = None) -> Task:
        import uuid
        t = Task(
            id=f"t_{uuid.uuid4().hex[:8]}",
            created_at=_now(),
            status=QUEUED,
            workspace=workspace,
            spec=spec,
            prompt=prompt,
            parent=parent,
        )
        with self._lock:
            self._tasks[t.id] = t
        self._append(t)
        return t

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[Task]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)

    def update(self, task_id: str, **fields) -> Task | None:
        with self._lock:
            t = self._tasks.get(task_id)
            if not t:
                return None
            for k, v in fields.items():
                if hasattr(t, k):
                    setattr(t, k, v)
        # write the new state
        with self._lock, open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        return t

    def compact(self) -> int:
        """Rewrite the JSONL keeping only the newest line per task id.

        The append-only ledger grows unboundedly (a single task can emit a line
        per update — 901KB observed). Collapse to the latest state of each task.
        Returns the number of lines written.
        """
        latest: dict[str, Task] = {}
        for t in self._tasks.values():
            latest[t.id] = t
        with self._lock:
            tmp = self.path + ".tmp"
            count = 0
            with open(tmp, "w", encoding="utf-8") as fh:
                for t in sorted(latest.values(), key=lambda x: x.created_at):
                    fh.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
                    count += 1
            os.replace(tmp, self.path)
        return count

    def set_status(self, task_id: str, status: str, started: bool = False,
                   completed: bool = False, error: str | None = None) -> Task | None:
        fields: dict = {"status": status}
        if started and not self.get(task_id).started_at:
            fields["started_at"] = _now()
        if completed:
            fields["completed_at"] = _now()
        if error:
            fields["errors"] = self.get(task_id).errors + [error]
        return self.update(task_id, **fields)


store = TaskStore()