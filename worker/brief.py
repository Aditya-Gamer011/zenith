"""Zenith-side engineering-brief builder for the Antigravity worker.

Zenith takes the user's intent and turns it into a **structured task spec** that
it hands to the worker. The distilling of a raw request into a crisp engineering
brief is part of what makes handoff useful — Antigravity shouldn't have to
guess requirements.

`build_spec()` is the helper the model calls via the `agent_submit` tool. It
does NOT forward the raw user message.
"""
from __future__ import annotations

import re


def default_workspace(slug: str) -> str:
    """A new project dir under the worker's workspace root."""
    return f"/home/singh/peacos-workspaces/{slug}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "task"


def build_spec(
    task: str,
    workspace: str = "",
    requirements: list[str] | None = None,
    constraints: list[str] | None = None,
    acceptance: list[str] | None = None,
    deliverables: list[str] | None = None,
    technologies: list[str] | None = None,
    context: str = "",
    autonomy: str = "high",
    destructive_allowed: bool = False,
    ask_for_clarification: bool = True,
    model: str = "gemini-3.1-pro-high",
) -> dict:
    """Assemble a clean structured spec for the worker.

    Callers (the `agent_submit` tool + Zenith's delegation prompt) pass mostly
    free intent; defaults fill the rest.
    """
    return {
        "task": task.strip(),
        "workspace": workspace.strip() or default_workspace(slugify(task)),
        "requirements": requirements or [],
        "constraints": constraints or [],
        "acceptanceCriteria": acceptance or [],
        "deliverables": deliverables or [],
        "technologies": technologies or [],
        "context": context.strip(),
        "autonomy": autonomy.lower() if autonomy in ("high", "medium", "low") else "high",
        "destructive_allowed": bool(destructive_allowed),
        "ask_for_clarification": bool(ask_for_clarification),
        "model": model,
    }


def rating_for(task: str, existing_tools: list[str] | None = None) -> str:
    """Cheap heuristic: is this a task Antigravity should take, or Zenith inline?

    Returns 'worker' | 'inline'.
    """
    big_markers = re.compile(
        r"\b(build|create|develop|implement|write an? (app|server|cli|api|project|service)|\
        something like|full[ -]?(stack)?|project|refactor|port|migrat|debug|fix|repair|test|"
        r"integration|docker|deploy|set ?up|script|automate|repo|repository)\b",
        re.I,
    )
    if big_markers.search(task):
        return "worker"
    # anything clearly a "remind/email/calendar/query" stays inline
    daily = re.compile(r"\b(remind|email|calendar|weather|todo|note|search|list)\b", re.I)
    if daily.search(task):
        return "inline"
    return "worker" if len(task.split()) > 6 else "inline"