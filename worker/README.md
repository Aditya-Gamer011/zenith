# Zenith × Antigravity Worker (`zenith-worker`)

Zenith delegates engineering and coding tasks to Google Antigravity via its CLI. This
worker serves as the local transport seam: it runs on the host (so `agy` has access
to the user's Antigravity authentication in `~/.gemini`), exposes a lightweight REST API on
`127.0.0.1:8022`, and maintains a persistent task ledger.

```
USER ⇄ Zenith (port 8005)
         │  agent_* tools
         ▼
 zenith-worker (127.0.0.1:8022, host user)
         │  runs `agy` CLI
         ▼
 Antigravity agent (agy) — commands, files, browser, task-planning
```

## Status Model

`QUEUED → STARTING → RUNNING → COMPLETED`
                 `└→ WAITING_FOR_INPUT → RUNNING`
`RUNNING/WAITING → FAILED | CANCELLED`

Tasks are tracked in an append-only JSONL ledger in `worker/tasks.jsonl`.

## The `agy` Transport

`worker/agy.py` delegates directly to the Antigravity CLI binary:

- `agy --print <brief> --model gemini-3.1-pro-high --output-format stream-json --print-timeout 4h --add-dir <workspace>`
- Parses `init` (conversation_id), `step_update` (current_activity from
  step_type + text_delta), `result` (final output) — all stored live on the task.
- `send_followup` resumes an existing conversation with `agy --print <msg> --conversation <id>`.
- Workspaces default to `~/zenith-workspaces/<slug>` (configurable via `ZENITH_WORKSPACES_DIR`).

## REST API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/tasks` | Submit an engineering task from a structured spec |
| GET | `/tasks` | List all tasks (newest first) |
| GET | `/tasks/{id}` | Full task state & progress |
| GET | `/tasks/{id}/output` | Accumulated output text |
| GET | `/tasks/{id}/artifacts` | Discovered workspace artifacts & files |
| POST | `/tasks/{id}/followup` | Send a followup message into the active conversation |
| POST | `/tasks/{id}/cancel` | Cancel an in-flight task |
| GET | `/health` | Worker service liveness check |

## Cross-Platform Execution

### 1. Install Dependencies
```bash
python3 -m pip install -r worker/requirements.txt
```

### 2. Launching the Worker

#### Linux / macOS:
```bash
python3 -m worker.peacant
```

#### Windows (PowerShell):
```powershell
python -m worker.peacant
```

### 3. Linux systemd Service (Optional for 24/7 background operation)

Create `/etc/systemd/system/zenith-worker.service`:

```ini
[Unit]
Description=Zenith Antigravity Worker (REST API on 127.0.0.1:8022)
After=network.target

[Service]
Type=simple
User=%I
WorkingDirectory=/path/to/zenith
ExecStart=/usr/bin/env python3 -m worker.peacant
Restart=always
RestartSec=3
Environment=PATH=%h/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=AGY_BIN=%h/.local/bin/agy

[Install]
WantedBy=multi-user.target
```

### 4. macOS launchd (Optional)
Run as a LaunchAgent in `~/Library/LaunchAgents/com.zenith.worker.plist` targeting `python3 -m worker.peacant`.

### 5. Windows Background Service / Scheduled Task (Optional)
Run via PowerShell background job or Windows Task Scheduler at logon:
```powershell
Start-Process python -ArgumentList "-m", "worker.peacant" -WindowStyle Hidden
```

## Safety & Scoping

- Tasks execute strictly within the designated workspace directory.
- `destructive_allowed=False` by default; destructive file/git operations require explicit user approval.
- The brief instructs the agent never to push to production branches or publish packages unless Zenith explicitly commands it.
- Zenith reviews task outputs and diffs before applying any changes.