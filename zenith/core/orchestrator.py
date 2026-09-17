"""The Orchestrator: Zenith's brain.

Ties the provider, tool catalog, memory store, and sub-agents together into one
agent loop. Responsibilities:

  - Build a system prompt informed by Zenith's identity + stored memory.
  - Run a tool-augmented chat loop (provider.stream -> tool calls -> execute).
  - Shadow every exchange into the conversation log.
  - After each turn, run a lightweight memory-extraction pass to update the
    knowledge graph and long-term memory automatically.
  - Delegate deep work to specialist agents when the model requests it.

The orchestrator is deliberately thin: providers do the talking, tools do the
acting, the scheduler does proactive work.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Callable

from ..core import tools as tool_reg  # registry: call_tool, catalog, tool_names
from ..memory import store
from .config import settings
from . import provider
from .prompts import build_system_prompt, SYSTEM_PROMPT
from .server_prompts import EXTRACT_FACTS_SYSTEM, get_extract_facts_system

log = logging.getLogger("zenith.orchestrator")

MAX_ROUNDS = 6

# UltraThink: when the user says "ultrathink", Zenith is allowed to spend real
# compute — more reasoning rounds, a much larger token budget per answer, and
# a system-prompt nudge to think deeply before acting or writing.
ULTRATHINK_KEYWORDS = ("ultrathink", "ultra think", "deep think", "deepthink")
ULTRATHINK_ROUNDS = 14
ULTRATHINK_MAX_TOKENS = 8000
STANDARD_MAX_TOKENS = 1600


def tool_names() -> str:
    return ", ".join(sorted(tool_reg.TOOLS))


class Orchestrator:
    """The main loop. One instance per server; holds conversation shadow history."""

    # Lazy import so the confirmation module's own imports don't create a cycle.
    @staticmethod
    def _gate():
        from ..core.confirmation import ConfirmGate

        return ConfirmGate(timeout=settings.confirm_timeout)

    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self.confirm_gate = self._gate()

    # ───────────────────────────────────────────────────────────── brain entry

    def build_system_prompt(self) -> str:
        from datetime import datetime, timezone, timedelta
        import os
        from ..tools import system_info, computer
        mem = store.memory_summary()
        tz_name = getattr(settings, "user_timezone", "") or os.getenv("USER_TIMEZONE") or os.getenv("TZ", "Asia/Kolkata")
        try:
            from zoneinfo import ZoneInfo
            now_dt = datetime.now(ZoneInfo(tz_name))
        except Exception:
            ist = timezone(timedelta(hours=5, minutes=30))
            now_dt = datetime.now(ist)
        now = now_dt.strftime("%A, %d %B %Y, %I:%M:%S %p (%Z)")
        user_name = settings.user_name or "Friend"
        base_prompt = build_system_prompt()
        host_summary = system_info.format_host_summary()
        recent_cmds = computer.get_command_history(limit=5)
        cmd_history_txt = ""
        if recent_cmds:
            cmd_lines = [
                f"- [{c['timestamp']}] $ {c['command']} -> exit {c['exit_code']} ({c['status']}) [{c['duration_seconds']:.2f}s, cwd: {c['cwd']}]"
                for c in recent_cmds
            ]
            cmd_history_txt = "\n\nRecent Commands Executed in Session:\n" + "\n".join(cmd_lines)

        try:
            from ..services.context_engine import context_engine
            unified_ctx = context_engine.build_prompt_context()
        except Exception:
            unified_ctx = ""

        from ..agents.agent_service import DEPARTMENTS
        dept_lines = [f"- `{k}`: {v['description']}" for k, v in sorted(DEPARTMENTS.items())]
        try:
            custom_agents = store.list_custom_agents()
            if custom_agents:
                dept_lines.extend([f"- `{c['id']}` (Custom): {c.get('role_description', '')}" for c in custom_agents])
        except Exception:
            pass
        org_roster = "\n".join(dept_lines)

        return base_prompt + f"""

--- CURRENT CONTEXT ---
Today's Date & Local Time: {now}.
You are fully aware of the current date and time. Use this wall-clock time for all relative time references (today, tomorrow, this week, this month, upcoming events).
Workspace: {settings.workspace_dir}
Active Working Directory: {computer.get_active_cwd()}

Host & Server Environment:
{host_summary}{cmd_history_txt}

What I know about {user_name} (from memory):
{mem}{unified_ctx}

--- MULTI-AGENT ORGANIZATION & DELEGATION ---
You are the Chief Executive Orchestrator of Zenith, leading an organization of specialized departmental agents.
When {user_name} asks for domain-specific actions, delegate the mission to the appropriate departmental specialist using `delegate_task(department, task, context)`:
{org_roster}

You hold executive tools:
- `delegate_task`: Delegate domain missions to your specialists (communication, coding, hr, research, operations, productivity, creative, utility, or custom agents).
- `list_agents`: View the complete organization roster and tool counts.
- `get_agent_status`: Poll or inspect ongoing/completed agent missions.
- `update_user_profile`: Update {user_name}'s name or profile immediately.
- `memory` / `graph`: Maintain strategic long-term memory and knowledge graph relations.
- `switch_mode` / `get_mode`: Switch system operating modes.
- `get_setup_status` / `setup_secret`: Configure API keys and secrets.
- `zenith_docs`: Built-in documentation reference.

Always communicate warmly, concisely, and supportively with {user_name}. Synthesize reports from your specialists into clear, conversational summaries.""".strip("\n")


    async def handle(self, user_text: str, emit: Callable) -> str:
        """Process one user message and emit events to `emit` (awaitable callable).

        The whole turn runs under `self._lock`: the Orchestrator is a singleton
        shared by chat + voice sessions (main.py), so without the lock two
        concurrent turns could interleave history/messages and each answer the
        other's prompt.
        """
        async with self._lock:
            return await self._handle_locked(user_text, emit)

    async def _handle_locked(self, user_text: str, emit: Callable) -> str:
        self.history.append({"role": "user", "content": user_text, "ts": time.time()})
        store.log_conversation("user", user_text)

        # UltraThink signals a deep-reasoning request: drop the word from what
        # the model sees but spend way more compute on the turn.
        low = user_text.lower()
        ultrathink = any(k in low for k in ULTRATHINK_KEYWORDS)
        cleaned_user = user_text
        if ultrathink:
            for k in ULTRATHINK_KEYWORDS:
                cleaned_user = re.sub(re.escape(k), "", cleaned_user, flags=re.IGNORECASE)
            cleaned_user = cleaned_user.strip() or user_text.strip()

        max_rounds = ULTRATHINK_ROUNDS if ultrathink else MAX_ROUNDS
        max_tokens = ULTRATHINK_MAX_TOKENS if ultrathink else STANDARD_MAX_TOKENS

        system = self.build_system_prompt()
        if ultrathink:
            system += (
                "\n\n[ULTRATHINK] This request asked for deep reasoning. Think "
                "thoroughly before every step; this turn has an unbounded token "
                "budget. Generate the best, most complete, most polished result "
                "possible — the answer, file, or document, fully fleshed out. "
                "Prefer the highest-quality model and spend its compute freely. "
                "Do not rush, do not truncate, do not skip refinements."
            )
        messages: list[dict] = [{"role": "system", "content": system}]
        # Walk the history newest-first and keep the last ~12 user turns plus
        # whatever assistant/tool rows they need, instead of a flat -16 slice
        # (a heavy tool turn appends 5+ rows, so a flat slice would evict real
        # dialogue in favor of tool noise).
        recent: list[dict] = []
        for m in reversed(self.history):
            role = m.get("role")
            if role == "user":
                recent.append(m)
                if len(recent) >= 12:
                    break
            elif role in ("assistant", "tool") and recent:
                recent.append(m)
        for m in reversed(recent):
            if m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        # Last user message carries the cleaned (ultrathink-stripped) text.
        if messages[-1].get("role") == "user":
            messages[-1]["content"] = cleaned_user

        tool_specs = tool_reg.executive_catalog()
        final_text = ""
        executed_tool_names: set[str] = set()

        tier = "deep" if ultrathink else "standard"
        for _round in range(1, max_rounds + 1):
            if provider.PROVIDER_MODE == "antigravity":
                primary = provider.chat_stream_antigravity
            elif provider.FALLBACK_PREFER:
                primary = provider.chat_stream_fallback
            else:
                primary = provider.chat_stream
            result = await self._run_round(primary, messages, tool_specs, emit, tier=tier, max_tokens=max_tokens)
            # Error resilience matrix:
            #   antigravity      -> Worker offline/error → fallback to direct Gemini stream
            #   quota            -> Gemini keypool exhausted → retry on DeepSeek (when not already there)
            #   unavailable      -> models 404/5xx → retry on fallback as well
            #   fallback_failed  -> DeepSeek relay died while FALLBACK_PREFER=yes → retry Gemini once
            if result["error"] and primary == provider.chat_stream_antigravity:
                log.warning("Antigravity worker stream failed (%s); falling back to direct provider stream", result["error"])
                if emit:
                    await emit({"type": "provider_fallback", "message": "Worker unavailable — switching to direct model stream."})
                result = await self._run_round(provider.chat_stream, messages, tool_specs, emit, tier=tier, max_tokens=max_tokens)

            if result["error"] in ("quota", "unavailable") and not provider.FALLBACK_PREFER and provider.FALLBACK_API_KEY:
                if emit:
                    await emit({"type": "provider_fallback", "message": "Model quota hit — using fallback."})
                result = await self._run_round(provider.chat_stream_fallback, messages, tool_specs, emit, tier=tier, max_tokens=max_tokens)
            elif result["error"] == "fallback_failed" and not provider.FALLBACK_PREFER:
                pass  # not preferring fallback; nothing to retry — handled below.
            elif result["error"] == "fallback_failed":
                # Relay flap while preferring DeepSeek → don't end the turn, retry Gemini.
                if emit:
                    await emit({"type": "provider_fallback", "message": "DeepSeek relay failed — retrying Gemini."})
                result = await self._run_round(provider.chat_stream, messages, tool_specs, emit, tier=tier, max_tokens=max_tokens)

            final_text = "".join(result["text"]).strip()
            calls = [result["pending"][i] for i in dict.fromkeys(result["order"]) if i in result["pending"]]
            if not calls:
                # Fallback (text-only relay) sometimes emits tool calls as
                # <|tool_calls|><invoke name="..."/> markup in text. Parse it so
                # Zenith stays agentic even when Gemini is throttled.
                markup_calls = _parse_markup_calls(final_text)
                if markup_calls:
                    calls = [{"name": n, "args": a, "extra": {}, "id": ""}
                             for n, a in markup_calls]
            if calls:
                executed_tool_names.update(c["name"] for c in calls)
            if result["error"]:
                if emit:
                    await emit({"type": "error", "error": result["error"]})
                # A broken/partial stream must NOT run the tools it promised —
                # the deltas may have been truncated, so executing them would
                # fire half-formed actions on a garbled prompt.
                final_text = "My thinking engine hit a snag — try that again."
                break
            if not calls:
                break

            tc_list = []
            for k, c in enumerate(calls):
                tc = {"id": c.get("id") or f"call_{c['name']}_{k}", "type": "function",
                      "function": {"name": c["name"], "arguments": c["args"]}}
                if c.get("extra"):
                    tc["extra_content"] = c["extra"]  # Gemini requires the thought_signature
                tc_list.append(tc)
            messages.append({"role": "assistant", "content": final_text or None, "tool_calls": tc_list})

            # Run all pending tool calls CONCURRENTLY (like Claude Code) so the
            # agent can fire several tools at once and get them all back in one
            # round. Results feed straight back into the same conversation.
            async def run_one(k: int, c: dict) -> dict:
                call_id = c.get("id") or f"call_{c['name']}_{k}"
                if emit:
                    await emit({"type": "tool_start", "name": c["name"], "args": c["args"]})
                # Timebox: shell commands allow up to 305s; other tools cap at 45s.
                timeout_cap = 305.0 if c["name"] == "shell" else 45.0
                try:
                    res = await asyncio.wait_for(
                        tool_reg.call_tool(c["name"], _parse_args(c["args"]), emit=emit),
                        timeout=timeout_cap,
                    )
                except asyncio.TimeoutError:
                    res = {"ok": False, "error": f"Tool '{c['name']}' timed out after {int(timeout_cap)}s"}

                cancelled = bool(res.get("cancelled"))
                ok = bool(res.get("ok", False)) and not cancelled
                content = res.get("result") if ok else res.get("error", "Unknown error")
                if content is None:
                    content = ""

                if emit:
                    await emit({"type": "tool_result", "name": c["name"],
                                "ok": ok,
                                "cancelled": cancelled,
                                "content": content})
                return {
                    "tool_call_id": call_id,
                    "name": c["name"],
                    "ok": ok,
                    "cancelled": cancelled,
                    "content": content,
                }

            batched = await asyncio.gather(*(run_one(k, c) for k, c in enumerate(calls)))
            for tool_msg in batched:
                messages.append({"role": "tool", "tool_call_id": tool_msg["tool_call_id"], "content": tool_msg["content"]})

            # If user explicitly cancelled an action at confirmation gate
            cancelled_msgs = [b["content"] for b in batched if b.get("cancelled")]
            if cancelled_msgs:
                final_text = cancelled_msgs[0]
            elif not final_text:
                # If model produced no text before tool calls, hold output in reserve
                res_texts = [b.get("content", "") for b in batched if b.get("content")]
                if res_texts:
                    final_text = "\n".join(res_texts).strip()

        # Active Profile Intent Guard:
        # If user asked to fix/change their name or dashboard profile, or if assistant promised
        # "let me update your profile", ensure update_user_profile is actually executed!
        if "update_user_profile" not in executed_tool_names:
            name_m = re.search(r"(?:call me|my name is|change my name to|update my name to)\s+([A-Za-z]+)", user_text, re.IGNORECASE)
            dashboard_fix = bool(re.search(r"dashboard\s+(?:still\s+)?says|fix\s+(?:the\s+)?(?:name|dashboard)", user_text, re.IGNORECASE))
            promised_update = bool(re.search(r"let me update your (?:user )?profile|updating your (?:user )?profile|update your profile right away", final_text, re.IGNORECASE))

            target_name = ""
            if name_m:
                target_name = name_m.group(1).strip().capitalize()
            elif dashboard_fix or promised_update:
                mem_name = store.get_memory("user", "name")
                if mem_name and mem_name.lower() not in ("maya", "friend", ""):
                    target_name = mem_name.strip()
                elif "aditya" in user_text.lower() or "aditya" in final_text.lower():
                    target_name = "Aditya"

            if target_name and target_name.lower() != settings.user_name.lower():
                try:
                    if emit:
                        await emit({"type": "tool_start", "name": "update_user_profile", "args": {"name": target_name}})
                    res = await tool_reg.call_tool("update_user_profile", {"name": target_name})
                    ok = bool(res.get("ok", True)) if isinstance(res, dict) else True
                    content = res.get("result", f"Profile updated: {target_name}") if isinstance(res, dict) else str(res)
                    if emit:
                        await emit({"type": "tool_result", "name": "update_user_profile", "ok": ok, "content": content})
                    if promised_update or dashboard_fix:
                        final_text += f"\n\n✓ Profile and dashboard updated — your name is now set to **{target_name}**."
                except Exception as exc:
                    log.warning("Active Profile Intent Guard failed to update profile: %s", exc)

        if not final_text:
            final_text = "Done."

        self.history.append({"role": "assistant", "content": final_text, "ts": time.time()})
        store.log_conversation("assistant", final_text)
        await self._extract_and_save(user_text, final_text)
        return final_text

    async def _run_round(self, streamer, messages, tool_specs, emit, tier: str = "standard", max_tokens: int = STANDARD_MAX_TOKENS) -> dict:
        """Stream one round; yields pending tool calls + text."""
        pending: dict[int, dict] = {}
        order: list[int] = []
        text_parts: list[str] = []
        error = None
        quota = False

        async for evt in streamer(tier, messages, tool_specs, max_tokens=max_tokens):
            et = evt.get("type")
            if et == "text":
                text_parts.append(evt.get("text", ""))
                if emit:
                    await emit({"type": "text", "text": evt.get("text", "")})
            elif et == "tool_call":
                idx = evt["index"]
                order.append(idx)
                fn = evt.get("function", {})
                pending[idx] = {"name": fn.get("name", ""), "args": fn.get("arguments", ""),
                                "extra": evt.get("extra") or {}, "id": evt.get("id") or ""}
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
                if evt.get("error") == "quota":
                    quota = True
                error = evt.get("error") or "provider error"

        return {"pending": pending, "order": order, "text": text_parts,
                "error": error, "quota": quota}

    # ── lifecycle / memory extraction

    def restart(self) -> None:
        self.history.clear()

    async def _extract_and_save(self, user_text: str, reply: str) -> None:
        """Fire-and-forget memory extraction via the fast model."""
        try:
            user_label = settings.user_name or "Friend"
            excerpt = f"{user_label}: {user_text[:1500]}\nZenith: {reply[:1500]}"
            result = await provider.chat_once(
                "fast",
                [{"role": "system", "content": get_extract_facts_system(user_label)},
                 {"role": "user", "content": f"Extract durable facts about {user_label} from:\n{excerpt}"}],
                max_tokens=900,
            )
            parsed = _attempt_json_decode(result)
            if not parsed:
                log.debug("no memory extraction result")
                return
            for mem in parsed.get("memory", []):
                cat = str(mem.get("category", "general")).strip()
                key = str(mem.get("key", "")).strip()
                value = str(mem.get("value", "")).strip()
                if key and value:
                    store.save_memory(cat or "general", key, value)
            for rel in parsed.get("graph", []):
                src = str(rel.get("source", "")).strip()
                tgt = str(rel.get("target", "")).strip()
                r = str(rel.get("rel", "related_to")).strip()
                if src and tgt:
                    store.add_relation(src, r or "related_to", tgt)
        except Exception as exc:
            log.debug("memory extraction failed: %s", exc)

        try:
            from ..services.memory_layer import memory_layer
            memory_layer.distill_turn(user_text, reply)
        except Exception as exc:
            log.debug("mem0 distill turn failed: %s", exc)


def _attempt_json_decode(text: str) -> dict | None:
    if not text:
        return None
    for candidate in (text, _first_braces_block(text)):
        try:
            val = json.loads(candidate)
            if isinstance(val, dict):
                return val
        except Exception:
            continue
    return None


def _first_braces_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _parse_args(raw: str) -> dict:
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        if isinstance(val, dict):
            return val
    except Exception:
        pass

    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    parsed = {}
    current_key = None
    current_val_lines: list[str] = []

    known_keys = ("to", "subject", "body", "command", "url", "query", "path",
                  "action", "task", "container", "service", "repo", "owner", "title", "text")

    for line in lines:
        parts = line.split(":", 1)
        k_candidate = parts[0].strip().lower()
        if len(parts) == 2 and k_candidate in known_keys:
            if current_key:
                parsed[current_key] = "\n".join(current_val_lines).strip()
                current_val_lines = []
            current_key = k_candidate
            current_val_lines.append(parts[1].strip())
        elif current_key:
            current_val_lines.append(line)

    if current_key:
        parsed[current_key] = "\n".join(current_val_lines).strip()

    if parsed:
        return parsed

    return {"raw": raw}


# DeepSeek wraps tool calls in fences. Some relays (llmsolutions) render them
# with full-width vertical bars (｜, U+FF5C) as `<｜invoke` instead of `<|invoke`
# — match all three bar styles (ASCII |, box-drawing │ U+2502, full-width ｜
# U+FF5C), plus the <invoke/> self-closing and <invoke>…</invoke> forms.
_BAR = r"[|│｜]"
_MARKUP_RE = re.compile(
    rf"<\s*{_BAR}?\s*invoke\s+name=\"([^\"]+)\"\s*/>"
    rf"|<\s*{_BAR}?\s*invoke\s+name=\"([^\"]+)\"\s*>(.*?)</\s*{_BAR}?\s*invoke\s*>",
    re.S,
)


_PARAM_RE = re.compile(r"<\s*[|│｜]?\s*parameter\s+name=\"([^\"]+)\"(?:[^>]*string=\"true\")?>(.*?)</\s*[|│｜]?\s*parameter\s*>", re.S)


def _markup_args(args_raw: str) -> str:
    """Convert <parameter name="x" string="true">v</parameter> markup to a JSON object.

    DeepSeek relays often emit args as repeated parameter tags instead of a
    JSON string. Best-effort: turn them into {"x": "v", ...}; fall back to the
    raw string when that fails so unknown shapes still reach the tool.
    """
    args_raw = (args_raw or "").strip()
    if not args_raw:
        return "{}"
    params = _PARAM_RE.findall(args_raw)
    if not params:
        return args_raw
    obj = {k.strip(): v.strip() for k, v in params if k.strip()}
    try:
        return json.dumps(obj, ensure_ascii=False)
    except Exception:
        return args_raw


def _parse_markup_calls(text: str) -> list[tuple[str, str]]:
    """Parse DeepSeek-style <invoke name="tool"> args </invoke> markup."""
    out: list[tuple[str, str]] = []
    if not text:
        return out
    for m in _MARKUP_RE.finditer(text):
        name = (m.group(1) or m.group(2) or "").strip()
        args_raw = m.group(3) or ""
        out.append((name, _markup_args(args_raw)))
    return out