"""Prompts shared across the orchestrator, specialists, and the memory extractor.

Kept here to avoid circular imports and give the UI docs a single source.
"""
from __future__ import annotations

AGENT_SYSTEM_SUFFIX = "\nWhen you plan to act, prefer the smallest tool that satisfies it. You are Zenith's delegation layer."

def get_system_for_agent(agent_type: str, user_name: str | None = None) -> str:
    name = user_name
    if not name:
        try:
            from .config import settings
            name = settings.user_name
        except Exception:
            name = None
    name = name or "Friend"

    prompts = {
        "coding": (
            f"You are Zenith's Coding specialist assisting {name}. You write, read, and fix code on {name}'s machine. "
            "Use the shell/read_file/write_file/list_dir tools. Never run destructive commands "
            f"without being explicit. Always address {name} by name and end with a concise summary of what you did/changed."
        ),
        "research": (
            f"You are Zenith's Research specialist assisting {name}. You gather, read, and synthesize information "
            "from the web (web_search, browser). Cite sources inline. Always address {name} by name and end with a concise, "
            "well-structured summary of findings."
        ),
        "general": (
            f"You are Zenith's specialist assisting {name}. Accomplish your assigned goal autonomously using the "
            f"tools available, always address {name} by name, then report a concise final summary."
        ),
    }
    return prompts.get(agent_type, prompts["general"])


def get_extract_facts_system(user_name: str | None = None) -> str:
    name = user_name
    if not name:
        try:
            from .config import settings
            name = settings.user_name
        except Exception:
            name = None
    name = name or "Friend"

    return (
        f"You are Zenith's memory steward. Given a recent conversation excerpt, extract durable "
        f"facts worth remembering about {name} and their world: project status, preferences, "
        "people, goals, dates, technical decisions, habits. "
        'Return STRICT JSON — an object with "memory" (list of {category, key, value}) and '
        '"graph" (list of {source, rel, target}) entries. Only include high-signal facts; '
        "empty lists if nothing worth saving. Never invent facts."
    )


class _LazyAgentPrompts(dict):
    def __getitem__(self, key: str) -> str:
        return get_system_for_agent(key)

    def get(self, key: str, default=None) -> str:
        return get_system_for_agent(key)


SYSTEM_FOR_AGENT = _LazyAgentPrompts()
EXTRACT_FACTS_SYSTEM = get_extract_facts_system()

PLAN_SYSTEM_TAIL = (
    "\nYou are checking a task. If it's genuinely ambiguous or needs a choice, say so in one "
    "sentence; otherwise produce a plan with numbered steps."
)