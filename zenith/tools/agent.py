"""Agent tools: executive delegation & HR agent lifecycle management.

Enables the Orchestrator to delegate tasks to specialized departmental units,
and enables the HR Agent (Agent Forge) to dynamically hire, configure, inspect,
and retire custom agents with SQLite persistence.
"""
from __future__ import annotations

import asyncio
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
            return (
                f"### ⚠️ Specialist Report: {dept.title()}\n"
                f"- **Status**: ❌ Execution Issue\n"
                f"- **Error Details**: {err}\n"
                f"💡 *Zenith can reformulate the mission or assign an alternative department.*"
            )
        
        agent_name = res.get("agent", dept)
        tool_calls = res.get("tool_calls", 0)
        output = res.get("result", "").strip()
        return (
            f"### 📋 [{agent_name} Report ({tool_calls} tool steps)]\n"
            f"- **Department**: `{dept}` | **Status**: ✅ Completed Successfully\n\n"
            f"{output}"
        )
    else:
        run_id = await svc.start(dept, task, context=context, emit=emit)
        return f"Delegated task to '{dept}' in background (Run ID: #{run_id}). You can check status with get_agent_status."


async def delegate_parallel(
    tasks: list[dict[str, Any]] | str,
    context: str = "",
    emit: Any = None,
) -> str:
    """Delegate multiple domain tasks to departmental specialist agents simultaneously in parallel."""
    svc = _get_service()
    if isinstance(tasks, str):
        try:
            tasks = json.loads(tasks)
        except Exception:
            return "Error: 'tasks' parameter must be a list of task objects (e.g. [{'department': 'communication', 'task': '...'}, ...])."
    if not isinstance(tasks, list) or not tasks:
        return "Error: 'tasks' must be a non-empty list of task assignments."

    async def _run_item(item: dict[str, Any]) -> str:
        dept = (item.get("department") or "").strip().lower()
        t = (item.get("task") or "").strip()
        c = item.get("context", "") or context
        if not dept or not t:
            return f"- ⚠️ Invalid task assignment: {item}"
        res = await svc.execute_task(dept, t, context=c, emit=emit)
        agent_name = res.get("agent", dept)
        calls = res.get("tool_calls", 0)
        out = (res.get("result") or res.get("error") or "No output").strip()
        status_tag = "✓ Completed" if res.get("ok") else "⚠ Failed"
        return (
            f"### [{agent_name} — {status_tag} ({calls} tool steps)]\n"
            f"- **Mission Goal**: *{t}*\n\n"
            f"{out}"
        )

    results = await asyncio.gather(*(_run_item(t) for t in tasks))
    return (
        f"## 🌐 Organization Parallel Mission Summary ({len(tasks)} Specialists Deployed):\n\n"
        + "\n\n---\n\n".join(results)
        + "\n\n---\n*Strategic findings have been synchronized and recorded to the organizational blackboard.*"
    )


async def delegate_pipeline(
    steps: list[dict[str, Any]] | str,
    initial_context: str = "",
    emit: Any = None,
) -> str:
    """Execute a multi-stage sequential pipeline of specialized agent tasks.

    Each step runs strictly in order; outputs and deliverables of previous steps
    are automatically piped as context into subsequent steps. Use when steps
    depend on deliverables of prior steps (e.g. create presentation -> email links).
    """
    svc = _get_service()
    if isinstance(steps, str):
        try:
            steps = json.loads(steps)
        except Exception:
            return "Error: 'steps' parameter must be a list of step objects (e.g. [{'department': 'creative', 'task': '...'}, {'department': 'communication', 'task': '...'}])."
    if not isinstance(steps, list) or not steps:
        return "Error: 'steps' must be a non-empty list of sequential step assignments."

    accumulated_context = (initial_context or "").strip()
    step_reports: list[str] = []

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            return f"Error: step {idx} is invalid (expected object with 'department' and 'task')."
        dept = (step.get("department") or "").strip().lower()
        task = (step.get("task") or "").strip()
        if not dept or not task:
            return f"Error: step {idx} must specify both 'department' and 'task'."

        step_context = step.get("context", "") or ""
        if accumulated_context:
            combined_context = f"{step_context}\n\n[Previous Pipeline Steps Context & Deliverables]:\n{accumulated_context}".strip()
        else:
            combined_context = step_context

        res = await svc.execute_task(dept, task, context=combined_context, emit=emit)
        agent_name = res.get("agent", dept)
        calls = res.get("tool_calls", 0)
        output = (res.get("result") or res.get("error") or "No output").strip()
        ok = res.get("ok", False)
        status_tag = "✅ Completed" if ok else "❌ Failed"

        report = (
            f"### Step {idx}: [{agent_name}] — {status_tag} ({calls} tool steps)\n"
            f"- **Mission Goal**: *{task}*\n\n"
            f"{output}"
        )
        step_reports.append(report)

        if not ok:
            step_reports.append(
                f"\n⚠️ **Pipeline halted early at Step {idx}** due to execution failure in `{dept}`."
            )
            break

        # Accumulate deliverables for subsequent steps
        accumulated_context += f"\n--- Deliverables from Step {idx} ({agent_name}) ---\n{output}\n"

    return (
        f"## ⛓️ Sequential Pipeline Execution Summary ({len(step_reports)} steps processed):\n\n"
        + "\n\n---\n\n".join(step_reports)
    )


async def ask_specialist(
    department: str,
    question: str,
    context: str = "",
    emit: Any = None,
) -> str:
    """Consult another departmental specialist agent for peer assistance or domain expertise."""
    from ..agents.agent_service import current_agent_depth, current_agent_name
    svc = _get_service()
    dept = (department or "").strip().lower()
    if not dept:
        return f"Please specify a department to consult. Available: {', '.join(sorted(DEPARTMENTS.keys()))}"
    if not question:
        return "Please specify a question or query for the specialist."

    caller_depth = current_agent_depth.get()
    caller_name = current_agent_name.get()
    if caller_depth >= 2:
        return f"Peer consultation limit reached (depth {caller_depth} >= 2). Please proceed with your own toolset."

    peer_context = f"Consultation requested by peer agent '{caller_name or 'Specialist'}'."
    if context:
        peer_context += f"\nContext: {context}"

    res = await svc.execute_task(dept, question, context=peer_context, emit=emit, depth=caller_depth + 1)
    if not res.get("ok"):
        return f"Specialist '{dept}' returned an error: {res.get('error', 'Execution failed')}"
    return (
        f"### 🤝 [{res.get('agent', dept)} Consultation Response]:\n"
        f"- **Department**: `{dept}` | **Status**: ✅ Success\n\n"
        f"{res.get('result', '').strip()}"
    )



async def share_finding(
    topic: str,
    content: str,
    department: str = "",
) -> str:
    """Publish a strategic finding, discovered intelligence, or status report to the organizational blackboard."""
    from ..agents.agent_service import current_agent_name
    from ..memory import store
    dept = department or current_agent_name.get() or "Executive"
    if not topic or not content:
        return "Both 'topic' and 'content' are required to publish a finding."
    row_id = store.blackboard_publish(department=dept, topic=topic, content=content)
    return f"✓ Finding published to organizational blackboard (ID #{row_id}) under '{topic}' by {dept}."


async def query_findings(
    query: str = "",
    department: str = "",
    limit: int = 5,
) -> str:
    """Query recent findings from the shared organizational blackboard and stored artifacts."""
    from ..memory import store
    findings = store.blackboard_query(query=query, department=department, limit=limit)

    all_artifacts = store.list_artifacts(limit=30)
    matching_artifacts = []
    q = (query or "").strip().lower()
    for art in all_artifacts:
        title = (art.get("title") or "").lower()
        atype = (art.get("type") or "").lower()
        aid = (art.get("id") or "").lower()
        if not q or (q in title or q in atype or q in aid):
            matching_artifacts.append(art)

    if not findings and not matching_artifacts:
        return f"No findings or artifacts found matching '{query}'."

    sections = []
    if findings:
        lines = [f"### 📋 Organizational Blackboard ({len(findings)} findings):"]
        for f in findings:
            lines.append(f"- **#{f['id']} [{f.get('department', 'Agent')}] {f.get('topic', '')}** ({f.get('created_at', '')}):\n  {f.get('content', '')}")
        sections.append("\n\n".join(lines))

    if matching_artifacts:
        art_lines = [f"### 🎨 Discovered Artifacts & Deliverables ({len(matching_artifacts)} artifacts):"]
        for a in matching_artifacts[:limit]:
            web_url = a.get("web_url") or ""
            file_path = a.get("file_path") or ""
            title = a.get("title") or "Untitled Artifact"
            art_type = a.get("type", "file").upper()
            art_lines.append(
                f"- **{title}** [{art_type}] (ID: `{a.get('id')}`)\n"
                f"  - Local Web Viewer: {web_url or 'N/A'} *(local browser UI only)*\n"
                f"  - File Path: `{file_path}`\n"
                f"  - Email Attachment: Use `email_send(..., attachment_path='{file_path}')` *(ALWAYS attach file directly in emails)*"
            )
        sections.append("\n\n".join(art_lines))

    return "\n\n---\n\n".join(sections)




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