"""Agent tools: executive delegation & HR agent lifecycle management.

Enables the Orchestrator to delegate tasks to specialized departmental units,
and enables the HR Agent (Agent Forge) to dynamically hire, configure, inspect,
and retire custom agents with SQLite persistence.
"""
from __future__ import annotations

import json
from typing import Any

from ..agents.agent_service import AgentService, DEPARTMENTS
from ..core import tools as tool_reg
from ..memory import store

_service: AgentService | None = None


def _get_service() -> AgentService:
    global _service
    if _service is None:
        from ..core.services import get_agent_service

        _service = get_agent_service()
    return _service


# ─── Executive Orchestrator Tools ─────────────────────────────────────────────

async def delegate_task(
    department: str,
    task: str,
    context: str = "",
    synchronous: bool = True,
    emit: Any = None,
) -> str:
    """Delegate a mission to a specialized departmental agent or custom hired agent."""
    svc = _get_service()
    dept = (department or "").strip().lower()
    if not dept:
        return f"Please specify a department or agent name. Available: {', '.join(sorted(DEPARTMENTS.keys()))}"
    if not task:
        return "Please provide a task or mission description for the agent."

    if synchronous:
        res = await svc.execute_task(dept, task, context=context, emit=emit)
        if not res.get("ok"):
            err = res.get("error", "Task execution failed.")
            return f"Agent '{dept}' encountered an issue: {err}"
        
        agent_name = res.get("agent", dept)
        tool_calls = res.get("tool_calls", 0)
        output = res.get("result", "").strip()
        return f"[{agent_name} Report ({tool_calls} tool steps)]\n{output}"
    else:
        run_id = await svc.start(dept, task, context=context, emit=emit)
        return f"Delegated task to '{dept}' in background (Run ID: #{run_id}). You can check status with get_agent_status."



async def list_agents() -> str:
    """List all available agents in the organization (both built-in departments and custom hires)."""
    svc = _get_service()
    roster = svc.list_roster()
    if not roster:
        return "No agents registered."

    lines = ["### Zenith Organization Roster:"]
    lines.append("")
    lines.append("| Department / ID | Agent Name | Type | Tools | Primary Mission |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for a in roster:
        t_count = a.get("tool_count", len(a.get("tools", [])))
        atype = "Built-in" if a.get("type") == "builtin" else "Custom Hired"
        lines.append(f"| **{a['id']}** | {a['name']} | {atype} | {t_count} tools | {a['description']} |")

    return "\n".join(lines)


async def get_agent_status(run_id: str = "") -> str:
    """Check the status or fetch results of a background agent run."""
    svc = _get_service()
    if not run_id:
        runs = svc.list()
        if not runs:
            return "No active or recent agent runs."
        lines = ["Recent agent runs:"]
        for r in runs[:10]:
            lines.append(f"- #{r.id} ({r.name}): status={r.status}, steps={len(r.steps)}, tool_calls={r.tool_calls}")
        return "\n".join(lines)

    run = svc.get(run_id.strip().lstrip("#"))
    if not run:
        return f"Agent run '#{run_id}' not found."
    if run.status == "running":
        return f"Agent '{run.name}' (#{run.id}) is actively working (step {len(run.steps)}, {run.tool_calls} tool calls)."
    if run.error:
        return f"Agent '{run.name}' (#{run.id}) failed: {run.error}"
    return f"Agent '{run.name}' (#{run.id}) finished.\nResult:\n{run.result or 'No output.'}"


# ─── People Operations & HR (Agent Forge) Tools ───────────────────────────────

async def hire_agent(
    agent_id: str,
    name: str,
    department: str,
    role_description: str,
    system_prompt: str,
    tool_names: list[str] | None = None,
) -> str:
    """Create, hire, and register a new autonomous agent persisted to SQLite."""
    agent_id = (agent_id or "").strip().lower().replace(" ", "_")
    if not agent_id:
        return "Error: agent_id is required (e.g. 'security_auditor')."
    if agent_id in DEPARTMENTS:
        return f"Error: '{agent_id}' is a reserved built-in department name."
    if not name:
        name = agent_id.replace("_", " ").title()
    if not system_prompt:
        return "Error: system_prompt is required to define agent behavior and guidelines."

    tools_to_assign = tool_names or []
    if isinstance(tools_to_assign, str):
        try:
            tools_to_assign = json.loads(tools_to_assign)
        except Exception:
            tools_to_assign = [t.strip() for t in tools_to_assign.split(",") if t.strip()]

    # Validate tools against system catalog
    pool = tool_reg.TOOLS
    valid_tools = [t for t in tools_to_assign if t in pool]
    invalid_tools = [t for t in tools_to_assign if t not in pool]

    agent_data = {
        "id": agent_id,
        "name": name,
        "department": department or "Special Operations",
        "role_description": role_description or "Autonomous specialist",
        "system_prompt": system_prompt,
        "allowed_tools": valid_tools,
        "created_by": "HR",
    }

    ok = store.save_custom_agent(agent_data)
    if not ok:
        return f"Failed to persist custom agent '{agent_id}' to database."

    note = ""
    if invalid_tools:
        note = f"\nWarning: Ignored unrecognized tools: {', '.join(invalid_tools)}"

    return (
        f"✓ Successfully hired and registered agent '{name}' (#{agent_id}) in '{agent_data['department']}'!\n"
        f"- Tools allocated ({len(valid_tools)}): {', '.join(valid_tools) or 'None'}\n"
        f"- Status: Active & persisted. Zenith can now delegate to this agent using delegate_task(department='{agent_id}', task='...')."
        f"{note}"
    )


async def update_agent(
    agent_id: str,
    system_prompt: str = "",
    tool_names: list[str] | None = None,
    role_description: str = "",
) -> str:
    """Update system prompt, tools, or description of an existing custom agent."""
    agent_id = (agent_id or "").strip().lower()
    existing = store.get_custom_agent(agent_id)
    if not existing:
        return f"Agent '{agent_id}' not found in custom agents roster."

    if system_prompt:
        existing["system_prompt"] = system_prompt
    if role_description:
        existing["role_description"] = role_description
    if tool_names is not None:
        pool = tool_reg.TOOLS
        valid_tools = [t for t in tool_names if t in pool]
        existing["allowed_tools"] = valid_tools

    ok = store.save_custom_agent(existing)
    if not ok:
        return f"Failed to update agent '{agent_id}'."
    return f"✓ Updated agent '{existing['name']}' (#{agent_id}) successfully."


async def fire_agent(agent_id: str) -> str:
    """Retire and remove a custom agent from the organization."""
    agent_id = (agent_id or "").strip().lower()
    if agent_id in DEPARTMENTS:
        return f"Cannot fire core built-in department '{agent_id}'."
    existing = store.get_custom_agent(agent_id)
    if not existing:
        return f"Agent '{agent_id}' not found in custom agents roster."

    ok = store.delete_custom_agent(agent_id)
    if ok:
        return f"✓ Successfully retired and removed agent '{existing.get('name', agent_id)}' (#{agent_id})."
    return f"Failed to remove agent '{agent_id}'."


async def inspect_agent(agent_id: str) -> str:
    """Inspect full specification, prompt, and tool allocations for any agent."""
    svc = _get_service()
    prof = svc.get_agent_profile(agent_id)
    if not prof:
        return f"Agent '{agent_id}' not found."

    tools = prof.get("tools", [])
    return (
        f"### Agent Profile: {prof.get('name')} (`{prof.get('id')}`)\n"
        f"- **Department**: {prof.get('department')}\n"
        f"- **Type**: {prof.get('type')}\n"
        f"- **Description**: {prof.get('description')}\n"
        f"- **Tools ({len(tools)})**: {', '.join(sorted(tools))}\n\n"
        f"**System Prompt**:\n```\n{prof.get('system')}\n```"
    )


async def list_available_tools(filter: str = "") -> str:
    """List all available tools in the Zenith system catalog for HR tool allocation."""
    flt = (filter or "").lower()
    pool = tool_reg.TOOLS
    items = []
    for name, t in sorted(pool.items()):
        if flt and (flt not in name.lower() and flt not in t.get("description", "").lower()):
            continue
        desc = t.get("description", "").split(".")[0]
        items.append(f"- `{name}`: {desc}")

    if not items:
        return f"No tools matching filter '{filter}'."
    return f"### Zenith System Tool Catalog ({len(items)} tools):\n" + "\n".join(items)


# ─── Legacy Backward-Compatibility Tool ───────────────────────────────────────

async def agent(action: str, name: str = "", goal: str = "", context: str = "", agent_id: str = "") -> str:
    """Legacy subagent tool wrapper for backwards compatibility."""
    action = (action or "").lower()
    svc = _get_service()

    if action == "start":
        started_id = await svc.start(name or "utility", goal, context)
        return f"Agent started: {name or 'utility'} (#{started_id})."
    if action == "status":
        return await get_agent_status(agent_id or "")
    if action == "result":
        target_id = (agent_id or name or "").strip().lstrip("#")
        return svc.result(target_id)
    if action == "list":
        return await list_agents()
    return "Unknown agent action. Try 'start', 'status', 'result', or 'list'."