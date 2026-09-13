# Zenith × Antigravity Worker (`zenith-worker`)

Zenith hands substantial coding tasks to Google Antigravity via its CLI. This
worker is the transport seam: it runs as the **`singh` user** on the host
(so `agy` can use the user's Google login), exposes a small REST API on
`127.0.0.1:8022`, and keeps a persistent task ledger.

```
USER ⇄ Zenith (zenith, port 8000/8001)
         │  agent_* tools
         ▼
 zenith-worker (127.0.0.1:8022, user singh)
         │  runs `agy` CLI
         ▼
 Antigravity agent (agy) — commands, files, browser, task-planning
```

## Status model

`QUEUED → STARTING → RUNNING → COMPLETED`
                 `└→ WAITING_FOR_INPUT → RUNNING`
`RUNNING/WAITING → FAILED | CANCELLED`

Tasks are append-only JSONL in `worker/tasks.jsonl`.

## The `agy` transport

`worker/agy.py` shells out to `/home/singh/.local/bin/agy`:

- `agy --print <brief> --model gemini-3.1-pro-high --output-format stream-json --print-timeout 4h --add-dir <workspace>`
- Parses `init` (conversation_id), `step_update` (current_activity from
  step_type + text_delta), `result` (final output) — all stored live on the task.
- `send_followup` resumes a conversation with `agy --print <msg> --conversation <id>`.
- Workspaces default to `~/zenith-workspaces/<slug>` (trusted `/home/singh`).

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/tasks` | submit a task from a spec |
| GET | `/tasks` | list tasks |
| GET | `/tasks/{id}` | full task state |
| GET | `/tasks/{id}/output` | output text |
| GET | `/tasks/{id}/artifacts` | discovered files |
| POST | `/tasks/{id}/followup` | send a message into the conversation |
| POST | `/tasks/{id}/cancel` | cancel |
| GET | `/health` | liveness |

## Running

- Install deps: `python3 -m pip install -r worker/requirements.txt` (host, user singh)
- Start: `sudo systemctl enable --now zenith-worker` (needs the unit below) OR dev: `python3 -m worker.peacant`
- Needs `agy` in PATH and the user's Antigravity login (`~/.gemini`).

## systemd unit (`/etc/systemd/system/zenith-worker.service`)

```ini
[Unit]
Description=Zenith Antigravity Worker (REST API on 127.0.0.1:8022)
After=network.target

[Service]
Type=simple
User=singh
WorkingDirectory=/home/singh/Desktop/helper/zenith
ExecStart=/usr/bin/env python3 -m worker.peacant
Restart=always
RestartSec=3
Environment=PATH=/home/singh/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=AGY_BIN=/home/singh/.local/bin/agy

[Install]
WantedBy=multi-user.target
```

## Safety

- The agent runs whatever a task's brief tells it; by default `destructive_allowed=False`,
  `autonomy=high`, and the brief forbids production deploys/pushes unless Zenith says so.
- Zenith reviews the result and only applies changes the user asked for.