"""Agent tool: dispatch & poll specialist sub-agents (coding, research).

The tool talks to the AgentService, which actually runs the async LLM loop.
That keeps the registry decoupled from the runtime.
"""
from __future__ import annotations

from ..agents.agent_service import AgentService

_service: AgentService | None = None


def _get_service() -> AgentService:
    global _service
    if _service is None:
        from ..core.services import get_agent_service

        _service = get_agent_service()
    return _service


async def agent(action: str, name: str = "", goal: str = "", context: str = "", agent_id: str = "") -> str:
    action = (action or "").lower()
    svc = _get_service()

    if action == "start":
        if name not in ("coding", "research", "general"):
            return "Agent must be one of: coding, research, general."
        if not goal:
            return "Provide a goal for the agent."
        started_id = await svc.start(name, goal, context)
        return f"Agent started: {name} ({started_id}). I'll keep you posted with its status."
    if action == "status":
        agents = svc.list()
        if not agents:
            return "No agents running."
        lines = ["Active agents:"]
        for a in agents:
            lines.append(f"- {a.name} #{a.id}: {a.status}")
        return "\n".join(lines)
    if action == "result":
        target_id = (agent_id or name or "").strip()
        if not target_id:
            return "Provide an agent id for result."
        return svc.result(target_id)
    if action == "list":
        agents = svc.list()
        if not agents:
            return "No agents."
        return "\n".join(f"- {a.name} #{a.id}: {a.status}" for a in agents)
    return "Unknown agent action."