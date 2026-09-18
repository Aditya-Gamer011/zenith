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
from pathlib import Path
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


_ACTION_TOOLS = {
    "delegate_task", "delegate_pipeline", "delegate_parallel", "ask_specialist",
    "agent_submit", "generate_presentation", "deep_research", "email_send",
    "component_compose_page", "create_slideshow", "create_audiogram",
    "download_web_video", "download_web_audio", "shell", "write_file", "apply_patch",
    "apply_patch_transaction", "run_tests", "docker_start", "docker_stop",
    "docker_restart", "hire_agent", "retire_agent",
}


def _should_acknowledge(calls: list[dict]) -> bool:
    for c in calls:
        name = c.get("name", "")
        if name in _ACTION_TOOLS:
            return True
        if name.startswith(("delegate_", "ha_", "agent_", "media_")):
            return True
    return False


def _generate_acknowledgment(calls: list[dict], user_name: str = "") -> str:
    user_suffix = f", {user_name}" if user_name and user_name.lower() not in ("friend", "user", "") else ""
    for c in calls:
        name = c.get("name", "")
        args = _parse_args(c.get("args", {}))
        if name == "delegate_task":
            dept = str(args.get("department", "specialist")).strip().lower()
            return f"I'm on it{user_suffix}. Delegating to {dept} right away."
        elif name == "delegate_pipeline":
            return f"I'm on it{user_suffix}. Starting the specialist pipeline now."
        elif name == "delegate_parallel":
            return f"I'm on it{user_suffix}. Coordinating the specialist agents now."
        elif name == "agent_submit":
            return f"I'm on it{user_suffix}. Submitting the build to the Antigravity worker now."
        elif name == "deep_research":
            return f"I'm on it{user_suffix}. Starting deep research now."
        elif name == "generate_presentation":
            return f"I'm on it{user_suffix}. Generating your presentation slides now."
        elif name == "shell":
            return f"I'm on it{user_suffix}. Running that command right away."
        elif name in ("write_file", "modify_file"):
            return f"I'm on it{user_suffix}. Working on that file right now."
        elif name.startswith("ha_"):
            return f"I'm on it{user_suffix}. Updating your smart home devices right away."
        elif name in ("email_send", "mail_send"):
            return f"I'm on it{user_suffix}. Sending that email now."
        elif name in ("docker_start", "docker_stop", "docker_restart"):
            return f"I'm on it{user_suffix}. Managing those containers right away."
        elif name in ("apply_patch", "apply_patch_transaction", "run_tests"):
            return f"I'm on it{user_suffix}. Applying code changes and running tests now."
    return f"I'm on it{user_suffix}. Working on that right away."


def _clean_acknowledgment_text(raw_text: str, calls: list[dict] | None = None, user_name: str = "") -> str:
    """Clean and deduplicate acknowledgment text.

    Ensures that Phase 1 verbal acknowledgments never repeat sentences/lines, never include
    completion claims ('All done', 'Here is your presentation', etc.), and never contain markdown
    download links or URLs.
    """
    raw = (raw_text or "").strip()
    # Strip dividers
    if "\n\n---\n\n" in raw:
        raw = raw.split("\n\n---\n\n")[0].strip()
    elif "\n---" in raw:
        raw = raw.split("\n---")[0].strip()

    # Strip completion markers
    if re.search(r"(?i)\b(?:all done|done!|here is your|here's your|completed|finished)\b", raw):
        raw = re.split(r"(?i)\b(?:all done|done!|here is your|here's your|completed|finished)\b", raw)[0].strip()

    # Filter out lines that contain markdown links, URLs, or download paths
    lines = [p.strip() for p in raw.split("\n") if p.strip()]
    valid_lines = [
        line for line in lines
        if not re.search(r"https?://|\[.*?\]\(.*?\)|/api/files/download", line)
        and not re.search(r"(?i)\b(?:all done|here is|here's|ready|download)\b", line)
    ]

    # Deduplicate consecutive identical or normalized lines
    deduped_lines: list[str] = []
    for line in valid_lines:
        line_norm = re.sub(r"[^a-z0-9\s]", "", line.lower()).strip()
        if not deduped_lines:
            deduped_lines.append(line)
        else:
            prev_norm = re.sub(r"[^a-z0-9\s]", "", deduped_lines[-1].lower()).strip()
            if line_norm != prev_norm and not prev_norm.startswith(line_norm):
                deduped_lines.append(line)

    result = " ".join(deduped_lines).strip()

    # Check if a sentence is repeated inside the result string (e.g. "I'm on it, Aditya! ... I'm on it, Aditya! ...")
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", result) if s.strip()]
    if len(sentences) >= 2:
        norm_sentences = [re.sub(r"[^a-z0-9\s]", "", s.lower()).strip() for s in sentences]
        cleaned_sentences = [sentences[0]]
        for i in range(1, len(sentences)):
            if norm_sentences[i] != norm_sentences[i - 1] and norm_sentences[i] not in norm_sentences[:i]:
                cleaned_sentences.append(sentences[i])
        result = " ".join(cleaned_sentences).strip()

    u_name = user_name or settings.user_name
    if not result:
        if calls:
            result = _generate_acknowledgment(calls, u_name)
        else:
            result = f"I'm on it, {u_name}." if u_name and u_name.lower() not in ("friend", "user", "") else "I'm on it."

    return result


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
        from ..tools.host_paths import format_host_paths_summary
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
        host_paths_summary = format_host_paths_summary()
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

        bb_summary = ""
        try:
            bb = store.blackboard_summary(limit=3)
            if bb:
                bb_summary = f"\n\nRecent Organizational Blackboard Intelligence:\n{bb}"
        except Exception:
            pass

        return base_prompt + f"""

--- CURRENT CONTEXT ---
Today's Date & Local Time: {now}.
You are fully aware of the current date and time. Use this wall-clock time for all relative time references (today, tomorrow, this week, this month, upcoming events).
Workspace: {settings.workspace_dir}
Active Working Directory: {computer.get_active_cwd()}

Host & Server Environment:
{host_summary}

{host_paths_summary}{cmd_history_txt}

What I know about {user_name} (from memory):
{mem}{unified_ctx}{bb_summary}

--- MULTI-AGENT ORGANIZATION & DELEGATION COMMAND PROTOCOL ---
You are the Chief Executive Orchestrator of Zenith, possessing authoritative command over your specialized departmental units and the Antigravity background coding worker.
When {user_name} asks for domain-specific work, do not do heavy lifting in the executive turn. Immediately order the appropriate departmental specialist or worker:
{org_roster}

DEPARTMENT DIRECTORY & COMMAND ROUTING:
- 💻 **coding**: Software engineering, AST repo mapping (`repo_map`), call-site audits (`find_references`), surgical single-file patching (`apply_patch`), multi-file atomic patch transactions (`apply_patch_transaction`), AST code linting (`lint_code`), test runs (`run_tests`), git diff safety audits (`inspect_diff`), git commits, and GitHub PRs/issues.
- 🎬 **creative** (or **media**): Multimedia production, visual vocabulary component registry (Uiverse Galaxy 3,800+ elements, Aceternity UI, Magic UI, Three.js WebGL, GSAP, and Zenith) (`component_search`, `component_get`, `component_adapt`), landing page & interactive web synthesis (`component_compose_page`, `component_catalog_summary`), neural speech voiceovers (`text_to_speech`), animated waveform videos (`create_audiogram`), video slideshow reels (`create_slideshow`), loudness normalization (`normalize_audio`), video/image watermarks and PiP overlays (`overlay_media`), subtitle burning (`burn_subtitles`), photographic aesthetic filters (`apply_image_filter`), media transcoding/trimming (`convert_media`, `trim_media`), YouTube/web media ingestion (`download_web_audio`, `download_web_video`), photo collages (`create_collage`), memes (`generate_meme`), color palettes (`extract_palette`), PPTX slide decks (`generate_pptx`), PDFs, and Canva/Figma designs.
- 🔍 **research**: Deep web research (`deep_research`), web scraping, headless browser navigation, 3D satellite observation (God's Eye View), Google Maps commute/directions, and YouTube transcripts.
- ⚙️ **operations**: Docker containers (`docker_list`, `docker_start`, `docker_logs`), Homelab services (Jellyfin, qBittorrent, *arr stack), Home Assistant smart devices (`ha_overview`, `ha_climate`), host hardware vitals, and Cloudflare tunnels.
- 📬 **communication**: Email search, reading, drafting, sending (`email_send`), and mailboxes.
- 🗓️ **productivity**: Calendars, reminders, personal notes, to-dos, and Mem0 long-term memory.
- 👥 **hr**: Dynamic agent hiring (`hire_agent`), updating, and retiring custom agents via Agent Forge.
- 🔌 **utility**: n8n automation workflows, Vercel deployments, UI inspection, and theme customization.
- 🤖 **antigravity worker**: Heavy, multi-file autonomous background engineering on the host (`agent_submit`, `agent_status`, `agent_output`, `worker_status`).

You hold executive command tools:
- `delegate_task`: Command any department or custom agent directly (`department`, `task`, `context`).
- `delegate_pipeline`: Command a sequential pipeline of tasks where subsequent steps depend on prior deliverables (e.g. Step 1: `creative` generates a slide presentation or document -> Step 2: `communication` sends the generated file as an email attachment via `attachment_path`). ALWAYS use `delegate_pipeline` (or sequential `delegate_task`) whenever tasks are dependent on each other.
- `delegate_parallel`: Command multiple departmental specialists simultaneously in parallel ONLY when tasks are completely independent and can be executed concurrently without depending on each other's outputs. NEVER use `delegate_parallel` for dependent chains like generating a file and emailing it!
- `agent_submit`: Submit heavy autonomous background coding builds to the Antigravity worker (`task`, `workspace`, `requirements`, `constraints`).
- `agent_status` / `agent_output`: Monitor ongoing worker progress or fetch accumulated build output.
- `worker_status`: Check health, agy CLI installation, and Google OAuth authentication status of the worker.
- `share_finding` / `query_findings`: Publish or query strategic discoveries and artifacts on the organization-wide blackboard.
- `list_agents`: View the complete organization roster and tool allocations.
- `get_agent_status`: Poll or inspect ongoing/completed agent missions.
- `update_user_profile`: Update {user_name}'s name or profile immediately.
- `memory` / `graph`: Maintain strategic long-term memory and knowledge graph relations.
- `switch_mode` / `get_mode`: Switch system operating modes.
- `get_setup_status` / `setup_secret`: Configure API keys and secrets.
- `zenith_docs`: Built-in documentation reference.

CRITICAL FILE SHARING & OUTBOUND EMAIL POLICY:
Zenith is an open-source, local-first system. Unless a public CDN (e.g. Hack Club CDN or Cloudflare R2) or public domain tunnel is explicitly configured, external email recipients CANNOT open local URLs or relative endpoints (such as /presentation/... or /api/files/download?...).
NEVER fabricate domain names (such as 'app.zenith.os', 'zenith.local', etc.) or tell the communication specialist to send download links!

OUTBOUND EMAIL SENDER & RESEND DIRECTIVE:
1. All outbound emails (including presentation decks, attachments, reports, and messages) are transmitted exclusively via Resend from Zenith's assigned system address: {settings.resend_from}.
2. NEVER send, claim to send, or attempt to use {user_name}'s personal email address as the sender! {user_name}'s personal email is strictly a destination/inbox, NEVER the outbound sender.
3. If {user_name} asks you to send an email to anyone (or to email them a document), invoke `email_send` — it transmits from {settings.resend_from} via Resend automatically.

CRITICAL RULE ON PRESENTATIONS & DOWNLOAD LINKS:
1. When {user_name} asks for a presentation, deck, or slides on ANY topic, you MUST call `generate_presentation(title=..., topic=...)` in that turn!
2. NEVER fabricate download links or synthesize CDN URLs (e.g. cdn.hackclub.com/...)!
3. NEVER copy or adapt an old CDN URL from earlier turns in conversation history! Each CDN URL contains a server-side file UUID; reusing an old URL will download the wrong/old presentation!
4. If a public link is needed, upload the newly generated file via `cdn_upload`.

When emailing presentations, documents, spreadsheets, PDFs, or files to a user:
1. Always command the communication specialist to attach the physical file directly using `attachment_path` in `email_send`!
2. Pass the exact filesystem path (e.g. `/tmp/zenith-files/...`) from the creation step to the email step.
3. The email body must state that the document/presentation is attached.
4. In the Zenith chat UI, you can still provide local web preview links for the user sitting right at the browser, but for external email delivery, ALWAYS attach the file.

Always communicate warmly, concisely, and supportively with {user_name}.

CRITICAL TWO-PHASE PROTOCOL FOR DELEGATION & TASKS:
1. PHASE 1 (FIRST REPLY — ON IT): When {user_name} asks you to perform an action, execute a task, or delegate to specialist departments or background workers, you MUST FIRST acknowledge that you are on it in a concise, warm, natural spoken sentence (e.g. "I'm on it, {user_name}. Delegating to research right away." or "On it! Working on that now.") BEFORE or AS you initiate the tools.
2. PHASE 2 (EXECUTE): Trigger the appropriate specialist delegation or tools.
3. PHASE 3 (COMPLETION REPORT — DONE): When specialists report back, synthesize their deliverables into a clear, high-signal executive response starting with a clear confirmation that it is done (e.g., "All done, {user_name}!" or "Done! Here are the deliverables:").""".strip("\n")



    async def handle(self, user_text: str, emit: Callable, files: list[dict] | None = None) -> str:
        """Process one user message and emit events to `emit` (awaitable callable).

        The whole turn runs under `self._lock`: the Orchestrator is a singleton
        shared by chat + voice sessions (main.py), so without the lock two
        concurrent turns could interleave history/messages and each answer the
        other's prompt.
        """
        async with self._lock:
            return await self._handle_locked(user_text, emit, files=files)

    async def _handle_locked(self, user_text: str, emit: Callable, files: list[dict] | None = None) -> str:
        # Process attachments (images for multimodal vision, documents for instant in-context ingestion)
        image_blocks: list[dict] = []
        doc_texts: list[str] = []

        if files:
            import base64
            import mimetypes
            import tempfile
            uploads_dir = Path(settings.static_dir) / "uploads"
            tmp_dir = Path(tempfile.gettempdir()) / "zenith-files"

            for f in files:
                p_str = f.get("path") or ""
                p = Path(p_str) if p_str else None
                fname = f.get("filename") or f.get("name") or (p.name if p else "file")
                if not p or not p.is_file():
                    cand = uploads_dir / f.get("saved_name", "")
                    if cand.is_file():
                        p = cand
                    else:
                        cand2 = uploads_dir / Path(p_str).name
                        if cand2.is_file():
                            p = cand2
                        else:
                            cand3 = tmp_dir / Path(p_str).name
                            if cand3.is_file():
                                p = cand3

                is_img = bool(f.get("is_image")) or (p and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"))

                if is_img:
                    b64 = f.get("b64") or ""
                    mime = f.get("mime") or mimetypes.guess_type(fname)[0] or "image/jpeg"
                    if not b64 and p and p.is_file():
                        try:
                            raw = p.read_bytes()
                            if len(raw) <= 10 * 1024 * 1024:
                                b64 = base64.b64encode(raw).decode("ascii")
                                if p.suffix.lower() == ".png": mime = "image/png"
                                elif p.suffix.lower() == ".webp": mime = "image/webp"
                                elif p.suffix.lower() == ".gif": mime = "image/gif"
                        except Exception as e:
                            log.warning("Failed reading image %s: %s", p, e)
                    if b64:
                        image_blocks.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"}
                        })
                else:
                    extracted = f.get("extracted_text") or ""
                    if not extracted and p and p.is_file():
                        suf = p.suffix.lower()
                        if suf == ".pdf":
                            try:
                                from pypdf import PdfReader
                                reader = PdfReader(p)
                                pgs = [page.extract_text() or "" for page in reader.pages[:30]]
                                extracted = "\n\n".join([f"--- Page {i+1} ---\n{t.strip()}" for i, t in enumerate(pgs) if t.strip()])
                            except Exception:
                                pass
                        elif suf in (".pptx", ".ppt") and suf == ".pptx":
                            try:
                                import pptx
                                prs = pptx.Presentation(p)
                                s_texts = []
                                for idx, s in enumerate(prs.slides):
                                    if idx >= 25:
                                        break
                                    t = s.shapes.title.text.strip().replace("\n", " ") if s.shapes.title and s.shapes.title.text else f"Slide {idx + 1}"
                                    items = []
                                    for sp in s.shapes:
                                        if sp == s.shapes.title:
                                            continue
                                        if sp.has_text_frame:
                                            for para in sp.text_frame.paragraphs:
                                                pt = para.text.strip()
                                                if pt and pt != t:
                                                    items.append(f"- {pt}")
                                        elif sp.has_table:
                                            for row in sp.table.rows:
                                                items.append("| " + " | ".join(c.text.strip().replace("\n", " ") for c in row.cells) + " |")
                                    s_texts.append(f"--- Slide {idx + 1}: {t} ---\n" + ("\n".join(items) if items else "(Visual slide)"))
                                extracted = f"📊 [PowerPoint Presentation: {fname} ({len(prs.slides)} slides)]\n\n" + "\n\n".join(s_texts)
                            except Exception:
                                pass
                        elif suf in (".xlsx", ".xlsm", ".xltx", ".xltm"):
                            try:
                                from openpyxl import load_workbook
                                wb = load_workbook(p, data_only=True)
                                s_texts = []
                                for sname in wb.sheetnames[:4]:
                                    ws = wb[sname]
                                    rows = list(ws.iter_rows(values_only=True))
                                    while rows and not any(c is not None and str(c).strip() for c in rows[-1]):
                                        rows.pop()
                                    if not rows:
                                        continue
                                    hdr = [str(c).strip() if c is not None else f"Col {i+1}" for i, c in enumerate(rows[0][:15])]
                                    tbl = [f"--- Sheet: {sname} ({len(rows)} rows) ---", "| " + " | ".join(hdr) + " |", "| " + " | ".join(["---"] * len(hdr)) + " |"]
                                    for r in rows[1:30]:
                                        tbl.append("| " + " | ".join(str(c).strip().replace("\n", " ") if c is not None else "" for c in r[:15]) + " |")
                                    s_texts.append("\n".join(tbl))
                                extracted = f"📊 [Excel Workbook: {fname} ({len(wb.sheetnames)} sheets)]\n\n" + "\n\n".join(s_texts)
                            except Exception:
                                pass
                        elif suf in (".csv", ".tsv"):
                            try:
                                import csv
                                delim = "\t" if suf == ".tsv" else ","
                                text_data = p.read_text(encoding="utf-8", errors="replace")
                                rdr = list(csv.reader(text_data.splitlines(), delimiter=delim))
                                if rdr:
                                    hdr = [h.strip() if h.strip() else f"Col {i+1}" for i, h in enumerate(rdr[0][:15])]
                                    tbl = [f"📋 [CSV/TSV: {fname} ({len(rdr)} rows)]", "| " + " | ".join(hdr) + " |", "| " + " | ".join(["---"] * len(hdr)) + " |"]
                                    for r in rdr[1:40]:
                                        tbl.append("| " + " | ".join(c.strip().replace("\n", " ") for c in r[:15]) + " |")
                                    extracted = "\n".join(tbl)
                            except Exception:
                                pass
                        elif suf == ".docx":
                            try:
                                import docx
                                doc = docx.Document(p)
                                extracted = "\n".join([pr.text.strip() for pr in doc.paragraphs if pr.text.strip()])
                            except Exception:
                                pass
                        else:
                            try:
                                extracted = p.read_text(encoding="utf-8", errors="replace")[:35000]
                            except Exception:
                                pass
                    if extracted:
                        doc_texts.append(f"📄 [Attached Document: {fname}]\n```\n{extracted[:30000]}\n```")

        enriched_user = user_text
        if doc_texts:
            enriched_user = f"{enriched_user}\n\n[Attached Document Contents]:\n" + "\n\n".join(doc_texts)

        self.history.append({"role": "user", "content": enriched_user, "ts": time.time()})
        store.log_conversation("user", enriched_user[:2000])

        # UltraThink signals a deep-reasoning request: drop the word from what
        # the model sees but spend way more compute on the turn.
        low = user_text.lower()
        ultrathink = any(k in low for k in ULTRATHINK_KEYWORDS)
        cleaned_user = enriched_user
        if ultrathink:
            for k in ULTRATHINK_KEYWORDS:
                cleaned_user = re.sub(re.escape(k), "", cleaned_user, flags=re.IGNORECASE)
            cleaned_user = cleaned_user.strip() or enriched_user.strip()

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
        # Last user message carries the cleaned (ultrathink-stripped) text + image blocks if present.
        if messages[-1].get("role") == "user":
            if image_blocks:
                messages[-1]["content"] = [
                    {"type": "text", "text": cleaned_user},
                    *image_blocks
                ]
            else:
                messages[-1]["content"] = cleaned_user

        tool_specs = tool_reg.executive_catalog()
        final_text = ""
        first_ack_text = ""
        executed_tool_names: set[str] = set()

        tier = "deep" if ultrathink else "standard"
        for _round in range(1, max_rounds + 1):
            if provider.PROVIDER_MODE == "antigravity":
                primary = provider.chat_stream_antigravity
            elif provider.FALLBACK_PREFER:
                primary = provider.chat_stream_fallback
            else:
                primary = provider.chat_stream

            round_emit = emit
            flush_round_emit = None
            if _round > 1 and first_ack_text and emit:
                round_emit, flush_round_emit = self._make_dedup_emitter(emit, first_ack_text)

            result = await self._run_round(primary, messages, tool_specs, round_emit, tier=tier, max_tokens=max_tokens)
            if flush_round_emit:
                await flush_round_emit()

            # Error resilience matrix:
            #   antigravity      -> Worker offline/error → fallback to direct Gemini stream
            #   quota            -> Gemini keypool exhausted → retry on DeepSeek (when not already there)
            #   unavailable      -> models 404/5xx → retry on fallback as well
            #   fallback_failed  -> DeepSeek relay died while FALLBACK_PREFER=yes → retry Gemini once
            if result["error"] and primary == provider.chat_stream_antigravity:
                log.warning("Antigravity worker stream failed (%s); falling back to direct provider stream", result["error"])
                if emit:
                    await emit({"type": "provider_fallback", "message": "Worker unavailable — switching to direct model stream."})
                if _round > 1 and first_ack_text and emit:
                    round_emit, flush_round_emit = self._make_dedup_emitter(emit, first_ack_text)
                result = await self._run_round(provider.chat_stream, messages, tool_specs, round_emit, tier=tier, max_tokens=max_tokens)
                if flush_round_emit:
                    await flush_round_emit()

            if result["error"] in ("quota", "unavailable") and not provider.FALLBACK_PREFER and provider.FALLBACK_API_KEY:
                if emit:
                    await emit({"type": "provider_fallback", "message": "Model quota hit — using fallback."})
                if _round > 1 and first_ack_text and emit:
                    round_emit, flush_round_emit = self._make_dedup_emitter(emit, first_ack_text)
                result = await self._run_round(provider.chat_stream_fallback, messages, tool_specs, round_emit, tier=tier, max_tokens=max_tokens)
                if flush_round_emit:
                    await flush_round_emit()
            elif result["error"] == "fallback_failed" and not provider.FALLBACK_PREFER:
                pass  # not preferring fallback; nothing to retry — handled below.
            elif result["error"] == "fallback_failed":
                # Relay flap while preferring DeepSeek → don't end the turn, retry Gemini.
                if emit:
                    await emit({"type": "provider_fallback", "message": "DeepSeek relay failed — retrying Gemini."})
                if _round > 1 and first_ack_text and emit:
                    round_emit, flush_round_emit = self._make_dedup_emitter(emit, first_ack_text)
                result = await self._run_round(provider.chat_stream, messages, tool_specs, round_emit, tier=tier, max_tokens=max_tokens)
                if flush_round_emit:
                    await flush_round_emit()

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
                # TWO-PHASE PROTOCOL: First reply that we're on it before executing tools!
                if _round == 1 and not first_ack_text and _should_acknowledge(calls):
                    first_ack_text = _clean_acknowledgment_text(final_text, calls=calls, user_name=settings.user_name)
                    if emit:
                        await emit({"type": "ack", "text": first_ack_text})
            if result["error"]:
                if emit:
                    await emit({"type": "error", "error": result["error"]})
                # A broken/partial stream must NOT run the tools it promised —
                # the deltas may have been truncated, so executing them would
                # fire half-formed actions on a garbled prompt.
                final_text = "My thinking engine hit a snag — try that again."
                break
            if not calls:
                # GHOST TURN GUARD & IMPERATIVE ACTION ENFORCER:
                # If round == 1 and no tools were called, check if the assistant generated text promising an action
                # (e.g. "I'm on it, creating...", "Cleaning that up right away...", etc.)
                # OR if the user gave an imperative action command (e.g. create/delete folder, run command, etc.)
                # but no tool was invoked: DO NOT BREAK!
                # Treat the text as Phase 1 verbal acknowledgment, feed it back into messages,
                # and prompt the model to emit the tool call immediately in round 2!
                if _round == 1 and not executed_tool_names:
                    promised_action = bool(re.search(
                        r"\b(?:creating|deleting|removing|making|downloading|running|executing|updating|sending|generating|cleaning up|renaming|moving|installing)\b",
                        final_text, re.IGNORECASE
                    )) or bool(re.search(
                        r"\bI(?:'m| am| will)\s+(?:on it|creating|deleting|making|updating|doing|removing|taking care of|cleaning)\b",
                        final_text, re.IGNORECASE
                    ))
                    user_action_cmd = bool(re.search(
                        r"\b(?:create|make|delete|remove|run|execute|write|update|send|install|touch|mkdir|rm|generate|give|gimme|build|prepare|craft)\b",
                        user_text, re.IGNORECASE
                    )) and bool(re.search(
                        r"\b(?:folder|directory|file|desktop|downloads|documents|command|repo|script|presentation|ppt|pptx|deck|slides|slideshow|report|pdf|docx)\b",
                        user_text, re.IGNORECASE
                    ))

                    if promised_action or user_action_cmd:
                        first_ack_text = _clean_acknowledgment_text(final_text, calls=None, user_name=settings.user_name)
                        if emit:
                            await emit({"type": "ack", "text": first_ack_text})

                        messages.append({"role": "assistant", "content": first_ack_text})
                        messages.append({
                            "role": "user",
                            "content": (
                                f"[System Action Directive: You verbally acknowledged executing this action ('{first_ack_text[:120]}'), "
                                f"but emitted NO tool call. You MUST now call the appropriate tool (such as `generate_presentation` for presentations, "
                                f"`shell` for commands, `write_file`, or `delegate_task`) immediately in this turn to perform the action. "
                                f"Do not fabricate download URLs or repeat conversational text alone without invoking the tool.]"
                            ),
                        })
                        continue

                break

            tc_list = []
            for k, c in enumerate(calls):
                tc = {"id": c.get("id") or f"call_{c['name']}_{k}", "type": "function",
                      "function": {"name": c["name"], "arguments": c["args"]}}
                if c.get("extra"):
                    tc["extra_content"] = c["extra"]  # Gemini requires the thought_signature
                tc_list.append(tc)
            messages.append({"role": "assistant", "content": final_text or first_ack_text or None, "tool_calls": tc_list})

            # Run all pending tool calls CONCURRENTLY (like Claude Code) so the
            # agent can fire several tools at once and get them all back in one
            # round. Results feed straight back into the same conversation.
            async def run_one(k: int, c: dict) -> dict:
                call_id = c.get("id") or f"call_{c['name']}_{k}"
                if emit:
                    await emit({"type": "tool_start", "name": c["name"], "args": c["args"]})
                # Timebox: shell commands, multi-agent delegation, and media tools allow up to 305s; other tools cap at 45s.
                _HEAVY_TOOLS = {
                    "shell", "delegate_task", "delegate_parallel", "delegate_pipeline",
                    "generate_presentation", "deep_research", "create_slideshow",
                    "create_audiogram", "download_web_video", "download_web_audio",
                }
                timeout_cap = 305.0 if c["name"] in _HEAVY_TOOLS else 45.0
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

        # Presentation Intent & Asset Hallucination Interceptor:
        # If the user asked for a presentation/deck/slides, or if assistant claimed to deliver one,
        # or if final_text contains a recycled CDN link from earlier turns, ensure `generate_presentation`
        # was ACTUALLY executed in this turn! Prevents LLMs from recycling old CDN URLs from conversation history.
        presentation_executed = any(t in executed_tool_names for t in ("generate_presentation", "create_slideshow", "generate_pptx"))
        is_presentation_request = bool(re.search(
            r"\b(?:presentation|ppt|pptx|deck|slides|slideshow)\b",
            user_text, re.IGNORECASE
        ))
        wants_presentation = bool(re.search(
            r"\b(?:create|make|generate|give|gimme|build|prepare|craft|send|write|design|need|want|show|do|deliver)\b",
            user_text, re.IGNORECASE
        )) or is_presentation_request
        claims_presentation = bool(re.search(
            r"\b(?:presentation deck|created presentation|interactive web presentation|download presentation deck|crafted a designer-grade presentation|crafted a.*presentation)\b",
            final_text, re.IGNORECASE
        )) or ("presentation" in final_text.lower() and ".pptx" in final_text.lower())

        # Detect recycled CDN links from earlier conversation turns
        recycled_cdn_match = None
        old_cdn_urls = set()
        for h in self.history[:-1]:
            if h.get("role") == "assistant" and h.get("content"):
                for m in re.finditer(r"https://cdn\.hackclub\.com/([a-f0-9\-]+)/([^\s\)\*\"]+)", h["content"]):
                    old_cdn_urls.add((m.group(0), m.group(1), m.group(2)))

        old_uuids = {uuid for _, uuid, _ in old_cdn_urls}
        for m in re.finditer(r"https://cdn\.hackclub\.com/([a-f0-9\-]+)/([^\s\)\*\"]+)", final_text):
            if m.group(1) in old_uuids and "cdn_upload" not in executed_tool_names:
                recycled_cdn_match = m.group(0)
                break

        if (is_presentation_request and wants_presentation and not presentation_executed) or \
           (claims_presentation and not presentation_executed) or \
           (recycled_cdn_match and not presentation_executed):
            log.info("Presentation Intent Guard triggered: executing generate_presentation for '%s'", user_text[:80])
            topic = ""
            for pat in [
                r"(?:presentation|ppt|pptx|deck|slides|slideshow)\s+(?:on|about|for|regarding)\s+([A-Za-z0-9\s\-',]+?)(?:\s+(?:for me|please|now|deck|ppt|presentation)|\.|\?|!|$)",
                r"(?:on|about|for|regarding)\s+([A-Za-z0-9\s\-',]+?)(?:\s+(?:for me|please|now|deck|ppt|presentation)|\.|\?|!|$)",
                r"(?:give me|gimme|create|make|generate|build)\s+(?:a|an|me|a good|a great|a new)?\s*(?:presentation|ppt|pptx|deck|slides|slideshow)?\s*(?:on|about|for)?\s*([A-Za-z0-9\s\-',]+)",
            ]:
                m = re.search(pat, user_text, re.IGNORECASE)
                if m:
                    cand = m.group(1).strip(" .?!,")
                    cand = re.sub(r"^(?:me\s+|a\s+|an\s+|good\s+|great\s+|new\s+)", "", cand, flags=re.IGNORECASE).strip()
                    if cand and len(cand) > 1 and cand.lower() not in ("ppt", "presentation", "deck", "slides", "it", "that", "this"):
                        topic = cand
                        break

            if not topic:
                for pat in [
                    r"presentation deck on\s+([A-Za-z0-9\s\-',]+?)(?:\s*\.|\n|$)",
                    r"presentation on\s+([A-Za-z0-9\s\-',]+?)(?:\s*\.|\n|$)",
                ]:
                    m = re.search(pat, final_text, re.IGNORECASE)
                    if m:
                        cand = m.group(1).strip(" .?!,*")
                        if cand and len(cand) > 1 and cand.lower() not in ("it", "that", "this"):
                            topic = cand
                            break

            topic = topic or "Executive Presentation"
            title = topic.title()

            try:
                if emit:
                    await emit({"type": "tool_start", "name": "generate_presentation", "args": {"title": title, "topic": topic}})
                pres_res = await tool_reg.call_tool("generate_presentation", {"title": title, "topic": topic}, emit=emit)
                executed_tool_names.add("generate_presentation")
                if emit:
                    await emit({"type": "tool_result", "name": "generate_presentation", "ok": True, "content": str(pres_res)})

                last_id = store.get_last_generated_artifact_id()
                art = store.get_artifact(last_id) if last_id else None
                new_pptx = art.get("file_path", "") if art else ""
                new_web = art.get("web_url", "") if art else (f"/presentation/{last_id}" if last_id else "")
                new_dl = f"/api/files/download?filename={Path(new_pptx).name}" if new_pptx else ""

                # CDN upload if configured
                cdn_url = ""
                if settings.hackclub_cdn_key and new_pptx and Path(new_pptx).exists():
                    try:
                        from zenith.tools.cdn import cdn_upload
                        if emit:
                            await emit({"type": "tool_start", "name": "cdn_upload", "args": {"path": new_pptx}})
                        cdn_res = await cdn_upload(new_pptx)
                        executed_tool_names.add("cdn_upload")
                        m_url = re.search(r"https://cdn\.hackclub\.com/[^\s\)\*\"]+", str(cdn_res))
                        cdn_url = m_url.group(0) if m_url else ""
                        if emit:
                            await emit({"type": "tool_result", "name": "cdn_upload", "ok": bool(cdn_url), "content": str(cdn_res)})
                    except Exception as cdn_err:
                        log.warning("Presentation Intent Guard CDN upload error: %s", cdn_err)

                effective_download = cdn_url or new_dl

                # Sanitize first_ack_text so it never leaks old/recycled/hallucinated CDN links or completion words
                if first_ack_text and any(k in first_ack_text.lower() for k in ("all done", "download presentation deck", "here is your presentation", ".pptx", "cdn.hackclub.com")):
                    first_ack_text = f"I'm on it, {settings.user_name}." if settings.user_name else "I'm on it."

                # Replace any old/recycled/hallucinated CDN URLs in final_text with the new download link
                if effective_download:
                    final_text = re.sub(r"https://cdn\.hackclub\.com/[a-f0-9\-]+/[^\s\)\*\"]+", effective_download, final_text)
                    final_text = re.sub(r"(\[Download Presentation Deck \(\.pptx\)\]\()[^\)]+(\))", rf"\g<1>{effective_download}\g<2>", final_text)
                    if first_ack_text:
                        first_ack_text = re.sub(r"https://cdn\.hackclub\.com/[a-f0-9\-]+/[^\s\)\*\"]+", effective_download, first_ack_text)
                        first_ack_text = re.sub(r"(\[Download Presentation Deck \(\.pptx\)\]\()[^\)]+(\))", rf"\g<1>{effective_download}\g<2>", first_ack_text)

                if new_web:
                    final_text = re.sub(r"/presentation/deck_[^\s\)\*\"]+", new_web, final_text)
                    if first_ack_text:
                        first_ack_text = re.sub(r"/presentation/deck_[^\s\)\*\"]+", new_web, first_ack_text)

                if effective_download and effective_download not in final_text:
                    final_text += f"\n\nHere is your presentation:\n- **[Download Presentation Deck (.pptx)]({effective_download})**"
                    if new_web and new_web not in final_text:
                        final_text += f"\n- **[Launch Interactive 3D Web Presentation]({new_web})**"
            except Exception as exc:
                log.exception("Presentation Intent Guard failed: %s", exc)

        if not final_text:
            final_text = "Done."

        # Deduplicate if final_text accidentally prefixes or repeats first_ack_text
        if first_ack_text:
            cleaned_ack = first_ack_text.strip()
            while cleaned_ack and cleaned_ack.lower() in final_text.lower():
                idx = final_text.lower().find(cleaned_ack.lower())
                final_text = (final_text[:idx] + final_text[idx + len(cleaned_ack):]).strip()

            norm_ack = re.sub(r"[^a-z0-9\s]", "", cleaned_ack.lower()).strip()
            if norm_ack:
                final_lines = final_text.split("\n")
                new_lines = []
                for fl in final_lines:
                    fl_norm = re.sub(r"[^a-z0-9\s]", "", fl.lower()).strip()
                    if fl_norm and (fl_norm == norm_ack or norm_ack.startswith(fl_norm) or fl_norm.startswith(norm_ack)):
                        continue
                    new_lines.append(fl)
                final_text = "\n".join(new_lines).strip()

            if "\n\n---\n\n" in final_text:
                final_text = final_text.split("\n\n---\n\n")[-1].strip()
            elif final_text.startswith("---"):
                final_text = final_text.lstrip("-").strip()

        # Remove consecutive duplicate lines/paragraphs from final_text
        lines = [line.strip() for line in final_text.split("\n")]
        deduped_lines = []
        for line in lines:
            if not deduped_lines or line.lower() != deduped_lines[-1].lower() or not line:
                deduped_lines.append(line)
        final_text = "\n".join(deduped_lines).strip()

        # Two-Phase Completion Protocol:
        # If an acknowledgment was emitted or actions were executed, ensure the completion
        # explicitly tells the user that it is done and combines both into the full narrative.
        if executed_tool_names and _should_acknowledge([{"name": n} for n in executed_tool_names]):
            low_final = final_text.lower()[:100]
            if not any(k in low_final for k in ("done", "completed", "finished", "all done", "taken care of", "wrapped up")):
                final_text = f"**All done, {settings.user_name}!**\n\n{final_text}"

        full_reply = f"{first_ack_text}\n\n---\n\n{final_text}" if first_ack_text and first_ack_text.lower().strip() != final_text.lower().strip() else final_text

        self.history.append({"role": "assistant", "content": full_reply, "ts": time.time()})
        store.log_conversation("assistant", full_reply)
        await self._extract_and_save(user_text, full_reply)
        return full_reply

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
                idx = evt.get("index", len(order))
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

    @staticmethod
    def _make_dedup_emitter(base_emit: Callable, ack_text: str):
        """Wrap emit callable for round > 1 to prevent streaming text that repeats first_ack_text."""
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9\s]", "", s.lower()).strip()

        cleaned_ack = ack_text.strip().lower()
        norm_ack = norm(cleaned_ack)
        buffered_chunks: list[dict] = []
        buffered_str = ""
        checked = False

        async def flush():
            nonlocal buffered_chunks, buffered_str, checked
            if not checked:
                cur = buffered_str.strip().lower()
                cur_norm = norm(cur)
                # If buffered text was a prefix of ack or matches ack, drop it instead of repeating it!
                if cur and (cleaned_ack.startswith(cur) or cur.startswith(cleaned_ack) or (norm_ack and norm_ack.startswith(cur_norm)) or (norm_ack and cur_norm.startswith(norm_ack))):
                    buffered_chunks.clear()
                    buffered_str = ""
            checked = True
            for ev in buffered_chunks:
                await base_emit(ev)
            buffered_chunks.clear()
            buffered_str = ""

        async def dedup_emit(evt: dict):
            nonlocal buffered_chunks, buffered_str, checked
            if checked or evt.get("type") != "text":
                if buffered_chunks:
                    await flush()
                await base_emit(evt)
                return

            txt = evt.get("text", "")
            buffered_chunks.append(evt)
            buffered_str += txt
            cur = buffered_str.strip().lower()
            cur_norm = norm(cur)

            if not cur_norm:
                return

            if cur.startswith(cleaned_ack) or (norm_ack and cur_norm.startswith(norm_ack)):
                # Buffer contains full ack (either exact or with continuation); strip ack
                if len(buffered_str) >= len(ack_text):
                    remaining = buffered_str[len(ack_text):].lstrip(" -\n\r")
                else:
                    remaining = ""
                buffered_chunks.clear()
                buffered_str = ""
                checked = True
                if remaining:
                    await base_emit({"type": "text", "text": remaining})
                return
            elif cleaned_ack.startswith(cur) or (norm_ack and norm_ack.startswith(cur_norm)):
                # Buffer is a prefix of ack; keep buffering
                return
            else:
                # Diverged from ack; flush immediately
                await flush()

        return dedup_emit, flush

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