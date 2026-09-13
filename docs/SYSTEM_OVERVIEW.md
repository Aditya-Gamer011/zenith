# Zenith · System Architecture & Capabilities

Zenith is an open-source, autonomous AI companion, sovereign command engine, and homelab control plane designed for general use. Built for privacy, resilience, and local execution, Zenith operates as a unified intelligence layer over a user's digital environment, media stacks, developer tools, and smart devices.

---

## 1. Core Architecture

Zenith is built around a decoupled, asynchronous, event-driven pipeline running on Python 3.11+ and FastAPI.

```
                    ┌───────────────────────────────────────┐
                    │      Zenith Web UI / Client           │
                    │  (HTML5 / Vanilla JS / Glassmorphism) │
                    └───────────────────┬───────────────────┘
                                        │
                         HTTP / REST    │   WebSocket (Live / Bidi)
                                        ▼
                    ┌───────────────────────────────────────┐
                    │         FastAPI Application           │
                    │     (zenith/main.py, port 8005)       │
                    └───────────────────┬───────────────────┘
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│     Orchestrator      │   │     Memory Engine     │   │   Proactive Daemon    │
│  (ReAct Tool Loop)    │   │  (SQLite Brain DB)    │   │  (Background Sweeps)  │
└──────────┬────────────┘   └───────────────────────┘   └───────────────────────┘
           │
           ├────────────────────────┬────────────────────────┐
           ▼                        ▼                        ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│ Primary LLM Provider  │ │ Dynamic Tool Registry │ │  Antigravity Worker   │
│  (Google Gemini 2.5/  │ │ (60+ Built-in Tools:  │ │  (Autonomous Coding   │
│  Live / Groq / Fallbacks) Docker, Maps, GitHub) │ │   Background Agent)   │
└───────────────────────┘ └───────────────────────┘ └───────────────────────┘
```

### 1.1 Web Layer & Real-time WebSocket Pump
- **Port**: `8005` (configurable via `PORT` or `ZENITH_PORT` in `.env`).
- **Endpoint**: `/ws` handles real-time bidirectional JSON messages for user prompts, streaming LLM token chunks, tool call execution events, and confirmation requests.
- **Voice Audio Streaming**: `/ws/live` connects directly to the Google Gemini Multimodal Live API WebSocket for ultra-low-latency bidirectional native audio streaming (PCM16).
- **Static Assets**: Pure HTML5, CSS3, and modern JavaScript (`/static`), featuring a monochrome matte and glassmorphic aesthetic with full Light and Dark mode parity.

### 1.2 ReAct Orchestrator (`zenith.core.orchestrator`)
- Implements an autonomous multi-turn reasoning and tool execution loop.
- Automatically selects, formats parameters, executes tools, and evaluates tool outputs until a comprehensive, actionable response is formed.
- Supports streaming replies directly to the client interface while managing tool calls transparently.
- Built with **Direct Execution**: Zenith executes requests immediately without conversational stalling, rhetorical questions, or unneeded previews.

### 1.3 Persistent Memory & Knowledge Graph (`zenith.memory.store`)
- **Database**: Embedded SQLite database (`jarvis_brain.db` or configured storage) requiring zero external database services.
- **Episodic Memory**: Stores conversation turns, user prompts, assistant answers, and tool executions.
- **Semantic Long-Term Facts**: Key-value knowledge store indexing user preferences, working directories, active projects, and system configurations.
- **Entity Knowledge Graph**: Triplet store (`subject`, `predicate`, `object`) linking entities, concepts, and relationships discovered across conversations.

### 1.4 Background Autonomy & Proactive Loops
- **Proactive Daemon (`zenith.core.proactive`)**: Periodically sweeps container health, scheduled calendar events, pending tasks, and system resource vitals.
- **Email Gateway (`zenith.core.email_gateway`)**: Autonomous inbound IMAP polling and triage. Analyzes sender importance, runs commands or workflows when authorized, and dispatches email notifications.

### 1.5 Antigravity Coding Worker (`zenith.worker`)
- A specialized autonomous coding agent capable of multi-file repository refactoring, diagnostic sweeps, test-driven implementations, and complex software builds in isolated workspaces.
- Orchestrator delegates large-scale engineering tasks via `agent_submit(task, workspace)` and tracks progress asynchronously via `agent_status` and `agent_artifacts`.

---

## 2. Multi-Model Intelligence & Fallbacks

Zenith is designed to remain permanently online regardless of API outages or rate limits:

1. **Primary LLM**: Google Gemini 2.5 Flash / Pro via Google AI Studio (`GEMINI_API_KEY`). Provides high-speed reasoning, 1M+ token context windows, and native tool execution.
2. **Native Live Voice**: Gemini Multimodal Live API (`LIVE_VOICE_ENABLED=yes`) for conversational real-time voice interaction.
3. **Voice STT & TTS Fallback**:
   - Speech-to-Text: Groq Whisper Large v3 Turbo (`GROQ_API_KEY`) for rapid audio transcription.
   - Text-to-Speech: Microsoft Edge Neural TTS (`TTS_PROVIDER=edgetts`) delivering natural human voices without cloud charges.
4. **Fallback LLM Relays**:
   - DeepSeek V3/V4 Flash or any OpenAI-compatible endpoint (`FALLBACK_API_KEY`, `FALLBACK_ENDPOINT`, `FALLBACK_MODEL`).
   - If Gemini encounters a 429 quota exhaustion or network timeout, Zenith automatically routes the turn to the fallback provider without dropping the conversation.

---

## 3. Privacy & Self-Sovereignty Principles

- **Zero Third-Party Telemetry**: Zenith communicates only with the API providers configured in your `.env` file. No tracking pixels, third-party analytics, or data telemetry.
- **Local Storage**: All chat transcripts, uploaded documents, generated presentations, and memory graphs remain on the host machine.
- **Confirmation Safeguards**: Mutating operations (such as container restarts, public DNS changes, repository creation, or host shell execution) can be gated with human-in-the-loop approvals.
