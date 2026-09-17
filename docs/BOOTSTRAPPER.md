# Zenith · Cross-Platform Unified Bootstrapper Reference

The **Zenith Bootstrapper** (`zenith-install.sh` for Linux & macOS, `zenith-install.ps1` for Windows) provides a single-command deployment pipeline that inspects the host, configures isolation boundaries, builds or verifies production containers, conducts health verification, and opens the user interface.

---

## 1. Single-Command Execution

### Remote Download & Run (Linux & macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/Aditya-Gamer011/zenith/main/zenith-install.sh | bash
```

### Local Execution (Linux & macOS)

```bash
# Clone the repository
git clone https://github.com/Aditya-Gamer011/zenith.git
cd zenith

# Execute bootstrapper directly
chmod +x zenith-install.sh
./zenith-install.sh
```

### Windows Execution (1-Click / Double-Click & CLI)

* **1-Click Double-Click**: Simply double-click **`zenith.exe`** or **`zenith.bat`** in Windows Explorer.
* **Command Prompt / Terminal**:
```cmd
zenith.exe
```
* **PowerShell 5.1 & PowerShell Core 7+**:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\zenith-install.ps1
```

---

## 2. The 8-Stage Bootstrap Pipeline

The installer executes 8 deterministic, idempotent stages with live terminal feedback:

```
[1/8] Detecting system
[2/8] Checking Docker
[3/8] Installing missing dependencies
[4/8] Validating Zenith configuration
[5/8] Building containers
[6/8] Starting services
[7/8] Waiting for health checks
[8/8] Opening Zenith
```

### Stage 1: Detecting System & Generating Local Profile
* Inspects host OS, distribution, architecture (`x86_64`, `aarch64`/`arm64`), kernel release, CPU core count, RAM (total, free), GPU availability (NVIDIA CUDA, Apple Silicon Metal, or CPU software rendering), active user, and shell.
* Automatically selects optimal worker concurrency:
  - **Low Memory** (`< 2 GB` RAM): 1 worker
  - **Standard Memory** (`2 GB – 8 GB` RAM): 2 workers
  - **High Memory** (`> 8 GB` RAM): 4 workers
* Compiles non-sensitive system metadata into a local profile at:
  ```
  ~/.zenith/system-info.json
  ```
* **Security Guarantee**: Strict filtration ensures that no passwords, API tokens, cryptographic keys, credentials, or session cookies are stored in this profile. Permissions are strictly locked to `0600` (read/write only for the owner).

### Stage 2: Checking Docker Engine & Automatic Ignition
* Verifies `docker` command availability and verifies daemon connectivity (`docker info`).
* **Automatic Engine Ignition**: If the Docker daemon is not running, the bootstrapper automatically starts it without requiring manual user commands:
  - **Windows**: Locates and starts `Docker Desktop.exe` via `Start-Process`, then polls for daemon readiness.
  - **Linux**: Starts the Docker systemd daemon (`systemctl start docker` or `service docker start`).
  - **macOS**: Launches Docker Desktop (`open -a Docker`).
* **Zero-Failure Native Fallback**: If Docker is not installed, cannot be started, or the user declines container installation, Zenith **automatically activates Zenith Native Host Mode** (`python run.py`), providing guaranteed 100% startup without downtime or failure.
* If Docker is missing and user approves, the bootstrapper:
  1. Explains what packages are required.
  2. Solicits user consent before requesting elevated privileges (`sudo`).
  3. Uses verified official package repositories for the target platform:
     - **Debian / Ubuntu / Raspberry Pi OS**: Official Docker convenience engine installer (`get.docker.com`).
     - **Fedora / RHEL / CentOS / Rocky**: Official `docker-ce` and containerd packages.
     - **Arch / Manjaro**: `pacman -Sy docker docker-compose`.
     - **Alpine Linux**: `apk add docker docker-cli-compose`.
     - **macOS**: Detects Homebrew (`brew install --cask docker`) or opens official Docker Desktop DMG.
     - **Windows**: Detects `winget install Docker.DockerDesktop` or guides through WSL2 integration.
  4. Enables and starts the `docker.service` systemd daemon where supported.
  5. Adds the current user to the `docker` group to prevent socket permission errors.

### Stage 3: Installing Missing Dependencies
* Tests for modern Docker Compose v2 (`docker compose version`).
* If missing, automatically retrieves the official modern Docker CLI Compose plugin into `~/.docker/cli-plugins/docker-compose` without polluting unrelated system directories.

### Stage 4: Validating Zenith Configuration
* **Disk Space**: Ensures at least 2.0 GB free disk space exists for image layers and data volumes.
* **Port Conflict Detection**: Tests port `8005`. If port `8005` is in use:
  - Checks whether it is an existing healthy Zenith instance (`http://localhost:8005/api/health`). If so, reports active operation.
  - If occupied by another process, alerts the user with PID diagnostics and instructions on setting `ZENITH_PORT` in `.env`.
* **Directory Structure**: Verifies `data/`, `data/memory/`, `static/screenshots/`, and `/tmp/zenith-files/`.
* **Configuration Sync**:
  - If `.env` is absent, creates it from `.env.example`.
  - If `.env` exists, scans `.env.example` and merges any missing keys with default values while **preserving all existing user credentials and configuration untouched**.
* **Key Validation**: Checks for `GEMINI_API_KEY`. If unconfigured, alerts the user that Zenith will start in Setup Mode (where the key can be pasted directly in the browser). Never echoes secrets to the terminal.

### Stage 5: Building Containers
* Detects existing `zenith:latest` production image. Reuses cached images during normal runs to ensure fast sub-second startup.
* When run with `--repair` or `--update`, triggers a pristine clean build (`docker compose build --no-cache`).

### Stage 6: Starting Services & Antigravity Coding Worker
* Automatically verifies or downloads the **Google Antigravity CLI** (`agy` or `agy.exe`) via official Google installers.
* Sets up a dedicated Python environment for the worker (`worker/.venv`) with `fastapi` and `uvicorn`.
* Spawns the **Antigravity Coding Worker** daemon (`zenith-worker` on host port 8022), enabling Zenith to delegate multi-file engineering and coding tasks.
* Connects the container stack to the host worker via universal `host.docker.internal:host-gateway` networking.
* Inspects existing container state (`docker compose ps`) and launches the stack:
  ```bash
  docker compose up -d
  ```

### Stage 7: Waiting for Health Checks
* Actively polls `http://localhost:8005/api/health` with a 45-second timeout and live progress indicators.
* Verifies HTTP 200 status and JSON payload (`"status": "ok"`).
* Verifies Antigravity Worker readiness and displays an onboarding tip if first-time Google sign-in is needed (`agy`).
* If health check fails or times out, immediately dumps the tail of container diagnostic logs with actionable troubleshooting advice.

### Stage 8: Opening Zenith & Desktop Shortcut
* Creates desktop shortcuts automatically:
  - **Windows**: Creates `Zenith.lnk` on the user's Desktop pointing directly to `zenith.exe`.
  - **Linux**: Creates `Zenith.desktop` on `$HOME/Desktop` and in `$HOME/.local/share/applications` with app icon and metadata.
* Dispatches platform-specific browser invocation:
  - **Linux**: `xdg-open http://localhost:8005`
  - **macOS**: `open http://localhost:8005`
  - **Windows / WSL**: `wslview` or `powershell Start-Process`
* If running in a headless or SSH terminal without GUI, skips browser opening cleanly and displays the terminal dashboard.

---

## 3. Command Reference & CLI Modes

The bootstrapper is fully idempotent and safe to execute repeatedly. Specialized maintenance modes can be invoked directly:

| Command | Action |
| :--- | :--- |
| `./zenith-install.sh` | Standard bootstrap: validates host, starts containers, verifies health, launches browser. |
| `./zenith-install.sh --repair` | Forces complete container rebuild with `--no-cache`, resets volume permissions, restarts. |
| `./zenith-install.sh --update` | Pulls latest Git commits, rebuilds container, restarts while **keeping all user memory & data intact**. |
| `./zenith-install.sh --uninstall` | Interactive, safe uninstaller. Asks confirmation before stopping containers or touching persistent volumes. |
| `./zenith-install.sh --stop` | Stops Zenith containers (`docker compose down`). |
| `./zenith-install.sh --restart` | Restarts Zenith container stack (`docker compose restart`). |
| `./zenith-install.sh --logs` | Streams live container runtime logs (`docker compose logs -f`). |
| `./zenith-install.sh --status` | Evaluates healthcheck endpoint and prints host system profile. |
| `./zenith-install.sh -y` | Non-interactive mode (auto-accepts prompts for CI/CD or headless automation). |

---

## 4. Production Container Architecture

Zenith's Docker architecture adheres to strict security standards:

```
                      ┌─────────────────────────────────────────┐
                      │              HOST SYSTEM                │
                      │  Port 8005:8005                         │
                      └────────────────────┬────────────────────┘
                                           │
                                           ▼
                      ┌─────────────────────────────────────────┐
                      │          zenith-core (Container)         │
                      │                                         │
                      │  • Non-root user: zenith (UID 10001)    │
                      │  • Minimal image: python:3.13-slim      │
                      │  • Security Opt: no-new-privileges:true │
                      │  • Listens on: 0.0.0.0:8005             │
                      │  • Healthcheck: curl /api/health        │
                      └───────┬─────────────────┬───────────────┘
                              │                 │
             ┌────────────────┴──────┐   ┌──────┴───────────────┐
             │  Named Volume Mounts  │   │ Opt-In Integrations  │
             ├───────────────────────┤   ├──────────────────────┤
             │ • zenith-data         │   │ (Off by default)     │
             │ • zenith-static       │   │ • /var/run/docker.sock│
             │ • zenith-files        │   │ • Host workspace     │
             └───────────────────────┘   └──────────────────────┘
```

### Key Security Safeguards
1. **Non-Root Runtime**: Container processes run under a dedicated system user `zenith` (UID 10001, GID 10001).
2. **Persistent Named Volumes**: User profile, SQLite memory graphs, and generated documents persist in isolated Docker volumes:
   - `zenith-data`: Stores SQLite databases, long-term memory, and user configurations.
   - `zenith-static`: Stores generated chart assets, screenshots, and visual outputs.
   - `zenith-files`: Stores generated PDFs, spreadsheets, presentations, and documents.
3. **Explicit Opt-In for Host Integrations**: Dangerous host capabilities (host Docker socket access, host shell execution) are disabled by default (`ALLOW_SHELL=no`, `ALLOW_DOCKER=no`). To grant container management permissions, the user explicitly configures `.env` and enables the read-only socket mount.
4. **Least Privilege System Isolation**: `security_opt: ["no-new-privileges:true"]` prevents privilege escalation within the container.

---

## 5. Troubleshooting & FAQ

### Port 8005 Already in Use
If port 8005 is occupied by another local service, you can change the port without modifying docker files:
```bash
# Set custom port in .env
echo "ZENITH_PORT=8080" >> .env

# Restart Zenith
./zenith-install.sh --restart
```

### Docker Permission Denied on Linux
If you encounter `permission denied while trying to connect to the Docker daemon socket`:
```bash
sudo usermod -aG docker $USER
newgrp docker
./zenith-install.sh
```

### Checking Container Logs
```bash
docker compose logs -f
```

### Rebuilding from Scratch
If files or dependencies were modified:
```bash
./zenith-install.sh --repair
```
