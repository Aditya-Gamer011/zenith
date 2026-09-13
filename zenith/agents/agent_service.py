"""Specialist agents: named LLM loops the orchestrator can delegate to.

An agent is a worker that takes a goal + a bounded toolset, runs a tool-augmented
conversation loop, and reports a final result. Specialization lives in *prompt +
toolset*, not separate processes — so agents are cheap to spawn and reason about.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from ..core import provider
from ..core import tools as tool_reg


@dataclass
class AgentRun:
    id: str
    name: str
    goal: str
    context: str = ""
    status: str = "queued"
    started_at: float = 0.0
    finished_at: float | None = None
    result: str = ""
    error: str = ""
    tool_calls: int = 0
    steps: list[dict] = field(default_factory=list)


_SYSTEM = {
    "coding": (
        "You are Zenith's Coding specialist. You write, read, and fix code on the user's machine. "
        "Use the shell/read_file/write_file/list_dir tools. Git ops are available via "
        "gh_issues/gh_pulls for repo context. Never run destructive commands without being "
        "explicit. End with a concise summary of what you did/changed."
    ),
    "research": (
        "You are Zenith's Research specialist. You gather, read, and synthesize information "
        "from the web (web_search, browser). Cite sources inline. End with a concise, "
        "well-structured summary of findings."
    ),
    "general": (
        "You are Zenith's specialist. Accomplish your assigned goal autonomously using the "
        "tools available, then report a concise final summary."
    ),
}

_TOOLSETS = {
    "coding": [
        "shell", "read_file", "write_file", "list_dir",
        "gh_issues", "gh_pulls", "gh_repo_status",
        "web_search", "browser", "notes", "todo",
    ],
    "research": [
        "web_search", "browser", "browser_screenshot",
        "gh_repo_status", "gh_list_repos", "gh_pulls",
    ],
    "general": [
        "web_search", "browser", "browser_screenshot",
        "system_status", "docker_list", "docker_status",
        "notes", "todo", "reminder", "calendar", "graph",
    ],
}


class AgentService:
    """Registry + async runner."""

    def __init__(self) -> None:
        self._runs: dict[str, AgentRun] = {}
        self._lock = asyncio.Lock()

    async def start(self, name: str, goal: str, context: str = "") -> str:
        if name not in _SYSTEM:
            name = "general"
        run = AgentRun(
            id=uuid.uuid4().hex[:8],
            name=name,
            goal=goal,
            context=context,
            started_at=time.time(),
        )
        async with self._lock:
            self._runs[run.id] = run
        asyncio.create_task(self._execute(run))
        return run.id

    def get(self, agent_id: str) -> AgentRun | None:
        return self._runs.get(agent_id)

    def list(self) -> list[AgentRun]:
        return sorted(self._runs.values(), key=lambda r: r.started_at, reverse=True)

    def result(self, agent_key: str) -> str:
        run = self._runs.get(agent_key)
        if run is None:
            return "Agent not found."
        if run.status == "running":
            return f"Agent {run.name} #{run.id} is still working (step {len(run.steps)})."
        if run.error:
            return f"Agent errored: {run.error}"
        return run.result or "No result."

    def _catalog(self, name: str) -> list[dict]:
        """Tool specs exposing only the tools an agent may use."""
        pool = tool_reg.TOOLS
        all_specs = {t["name"]: {
            "type": "function",
            "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
        } for t in pool.values()}
        allowed = _TOOLSETS.get(name, _TOOLSETS["general"])
        # Union with general so a coding agent always has the basics; the main
        # orchestrator stays unfiltered and the agent loop stays safe.
        allowed = list(dict.fromkeys([*allowed, *_TOOLSETS["general"]]))
        return [all_specs[t] for t in allowed if t in all_specs]

    async def _execute(self, run: AgentRun) -> str:
        run.status = "running"
        try:
            system = _SYSTEM.get(run.name, _SYSTEM["general"])
            if run.context:
                system += f"\nContext from the main brain:\n{run.context}"
            result = await self._run_loop(run, system)
            run.result = result
            run.status = "done"
        except Exception as exc:
            run.error = str(exc)
            run.status = "error"
        finally:
            run.finished_at = time.time()
        return run.result

    async def _run_fallback_round(self, system: str, messages: list[dict], run: AgentRun) -> str:
        """Finish a single round against the text-only fallback relay.

        The fallback doesn't expose structured tools, so we relay the recent
        messages and hand back the short answer. Enough to keep an agent from
        dying when Gemini is out of quota.
        """
        parts: list[str] = []
        async for evt in provider.chat_stream_fallback(
            "fast", messages, None, max_tokens=600,
        ):
            et = evt.get("type")
            if et == "text":
                parts.append(evt.get("text", ""))
            elif et == "error":
                return f"[agent fallback error] {evt.get('error')}"
        return "".join(parts).strip() or "Done."

    async def _run_loop(self, run: AgentRun, system: str) -> str:
        messages: list[dict] = [{"role": "system", "content": system}]
        messages.append({"role": "user", "content": run.goal})

        tools = self._catalog(run.name)
        final_text = ""
        max_rounds = 6

        # Primary model: honor FALLBACK_PREFER so agents ride DeepSeek when
        # configured, and keep the per-round quota fallback as backstop.
        primary = provider.chat_stream_fallback if provider.FALLBACK_PREFER else provider.chat_stream

        for _round in range(1, max_rounds + 1):
            pending: dict[int, dict] = {}
            order: list[int] = []
            text_parts: list[str] = []
            run.steps.append({"round": _round, "phase": "thinking"})

            async for evt in primary("standard", messages, tools, max_tokens=1400):
                et = evt.get("type")
                if et == "text":
                    text_parts.append(evt.get("text", ""))
                elif et == "tool_call":
                    idx = evt["index"]
                    order.append(idx)
                    pending[idx] = {
                        "name": evt.get("function", {}).get("name", ""),
                        "args": evt.get("function", {}).get("arguments", ""),
                        "extra": evt.get("extra") or {},
                        "id": evt.get("id") or "",
                    }
                elif et == "tool_delta":
                    idx = evt["index"]
                    if idx not in pending:
                        order.append(idx)
                        pending[idx] = {"name": "", "args": "", "extra": {}, "id": ""}
                    if evt.get("name"):
                        pending[idx]["name"] = evt["name"]
                    if evt.get("args"):
                        pending[idx]["args"] += evt["args"]
                    if evt.get("extra"):
                        pending[idx]["extra"] = evt.get("extra")
                elif et == "error":
                    if evt.get("error") == "quota" and provider.FALLBACK_API_KEY:
                        # Same graceful 429 fallback as the orchestrator: retry
                        # this round on the DeepSeek relay instead of dying.
                        run.steps.append({"round": _round, "summary": "provider fallback (quota)"})
                        final_round = await self._run_fallback_round(system, messages, run)
                        return final_round
                    return f"[agent error] {evt.get('error')}"

            final_text = "".join(text_parts).strip()
            calls = [pending[i] for i in dict.fromkeys(order) if i in pending]
            if not calls:
                # DeepSeek (fallback) emits tool calls as <invoke name="..."/>
                # markup in text when structured calls aren't present — parse it
                # so agents stay agentic on the fallback provider too.
                from ..core.orchestrator import _parse_markup_calls

                markup = _parse_markup_calls(final_text)
                if markup:
                    calls = [{"name": n, "args": a, "extra": {}, "id": ""} for n, a in markup]
            if not calls:
                return final_text or "No."

            tc_list = []
            for k, c in enumerate(calls):
                tc = {"id": c.get("id") or f"call_{c['name']}_{k}", "type": "function",
                      "function": {"name": c["name"], "arguments": c["args"]}}
                if c.get("extra"):
                    tc["extra_content"] = c["extra"]  # Gemini requires the thought_signature
                tc_list.append(tc)
            messages.append({"role": "assistant", "content": final_text or None,
                             "tool_calls": tc_list})
            async def run_one(k: int, c: dict) -> dict:
                run.tool_calls += 1
                run.steps.append({"round": _round, "summary": f"tool:{c['name']}", "args": c["args"][:120]})
                res = await tool_reg.call_tool(c["name"], _parse_args(c["args"]))
                return {"role": "tool", "tool_call_id": f"call_{c['name']}_{k}",
                        "content": res["result"] if res.get("ok") else res.get("error", "")}
            for tool_msg in await asyncio.gather(*(run_one(k, c) for k, c in enumerate(calls))):
                messages.append(tool_msg)

        return final_text or "Agent finished (reached max rounds)."


def _parse_args(raw: str) -> dict:
    import json
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}