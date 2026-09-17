# Zenith · Sovereign AI Operating Layer & Autonomous Command Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Playwright](https://img.shields.io/badge/Playwright-Automated%20Browser-45ba4b.svg)](https://playwright.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose%20Ready-2496ed.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-103%20Passed%20%7C%20100%25-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Zenith** is a proactive, sovereign AI operating layer, autonomous coding agent, and homelab command engine. Built from the ground up for privacy, local sovereignty, resilience, and multimodal real-time interaction, Zenith serves as an intelligent operating layer over your computer, applications, developer tools, media servers, and smart home devices.

Unlike chatbots that sit passively waiting for questions, Zenith actively maintains a **Unified Context Engine** across on-screen workflows, local activity timelines, long-term memory, camera vision, and autonomous browsers—while keeping you in absolute control through **Sovereign Privacy Guard** and **Ghost Mode**.

---

## 🌟 Key Highlights & Capabilities

### 1. 🛡️ Sovereign Operating Layer
- **Clippy Vision & Screen Awareness**: Passively tracks active application windows and workflow states (`coding`, `debugging`, `researching`, `designing`) with intelligent, throttled proactive suggestions.
- **ActivityWatch Local Timeline**: Private SQLite timeline recording application usage and durations without transmitting any telemetry off your machine.
- **Mem0 Multi-Tier Memory**: Structured long-term cognitive tiers (`preference`, `project`, `workflow`, `decision`) with automatic secret and credential redaction.
- **Unified Browser Engine**: Deterministic Playwright page navigation combined with autonomous multi-step **Browser Use** goal execution, gated by strict safety confirmation on sensitive operations (purchases, payments, account settings).
- **Real-World Vision & Gesture Approval**: Webcam presence detection, QR code/barcode scanning, and physical **thumbs-up gesture recognition** to approve destructive tool confirmations hands-free.
- **Sovereign Privacy Guard**: One-click **Ghost Mode** master kill-switch, granular sensor toggles, and protected application/domain blocklists (passwords, banking, identity providers).

### 2. 🛰️ God's Eye View (GEV) 3D Earth Observation
- Interactive 3D satellite visualization and tactical Earth observation console embedded directly in chat.
- Multispectral sensor overlays: FLIR (Thermal Infrared), NVG (Night Vision), CRT (Tactical Scanlines), Noir, and Snow.
- Live ADS-B flight tracking via OpenSky, maritime vessel tracking, and satellite telemetry.
- One-click full-screen expanding viewport and autonomous geocoding across global landmarks and coordinates.

### 3. ⚡ Autonomous AI Agent & Cross-Platform Execution
- Operates across **Linux (bash/sh)**, **macOS (zsh/bash)**, and **Windows (PowerShell/cmd)** with stateful working directory tracking.
- Self-inspecting command execution protocol: runs commands, parses structured output, diagnoses failures, and automatically determines next steps.
- Deep host introspection: automatically detects Docker containers, WSL2, Raspberry Pi, AWS, GCP, Azure, or native hardware.

### 4. 🧰 170+ Registered Tools in Unified Catalog
- **Developer & Cloud**: Git operations, GitHub Pro (`gh_create_pr`, `gh_code_review`, `gh_list_issues_prs`), Docker orchestration, Vercel deployments, Cloudflare Tunnels, R2 storage.
- **Web & Research**: Deep autonomous multi-query research with auto-extracted charts and downloadable PDF briefings (`deep_research`), full-page screenshots (`browser_screenshot`), structured page extraction (`web_extract_data`).
- **Productivity & Design**: PowerPoint presentation generation with web photos & custom themes (`generate_pptx`), document parsing (`analyze_file`), Figma & Canva OAuth plugins, PDF/Docx/XLSX generation.
- **Smart Home & Homelab**: Home Assistant climate/lighting/switches/smart plugs, Jellyfin streaming, Sonarr/Radarr/Prowlarr/qBittorrent automation.

---

## 📚 Complete Documentation

Comprehensive guides and architectural specifications are located in [`docs/`](./docs):

- **[Unified Bootstrapper Guide (`docs/BOOTSTRAPPER.md`)](./docs/BOOTSTRAPPER.md)**: Single-command cross-platform installer, 8-stage pipeline, system profile generation, and Docker orchestration.
- **[System Architecture & Overview (`docs/SYSTEM_OVERVIEW.md`)](./docs/SYSTEM_OVERVIEW.md)**: Deep dive into the FastAPI server, ReAct orchestrator loop, SQLite persistence, proactive background daemons, and multi-model failover.
- **[Complete Tools Reference (`docs/TOOLS_REFERENCE.md`)](./docs/TOOLS_REFERENCE.md)**: Schemas and parameter definitions for all 170+ built-in tools.
- **[Deployment & Getting Live (`docs/DEPLOYMENT_AND_SETUP.md`)](./docs/DEPLOYMENT_AND_SETUP.md)**: Docker Compose orchestration, Cloudflare Tunnels, Caddy reverse proxies, and systemd services.
- **[Integrations Setup (`docs/INTEGRATIONS_SETUP.md`)](./docs/INTEGRATIONS_SETUP.md)**: Step-by-step guides for connecting Figma, Canva, GitHub, Home Assistant, Cloudflare, and Google Maps.
- **[Brand & Design System (`docs/BRAND_KIT.md`)](./docs/BRAND_KIT.md)**: Glassmorphic UI specifications, color tokens, and layout guidelines.
- **[Agent Operational Manual (`docs/AGENT_GUIDE.md`)](./docs/AGENT_GUIDE.md)**: Zenith's autonomous execution handbook and safety protocols.

> **Pro Tip**: Zenith can read its own documentation at runtime! Simply ask questions in chat or let Zenith invoke `zenith_docs(topic)`.

---

## 🚀 Quickstart

### Option 1: Single-Command Bootstrapper (Recommended for Everyone)

Zenith includes an automated, idempotent bootstrapper that inspects your host, configures isolation, verifies health, and launches the browser in one step:

**Linux & macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/Aditya-Gamer011/zenith/main/zenith-install.sh | bash
# Or clone and run:
./start.sh   # (or ./zenith-install.sh)
```

**Windows (1-Click / Double-Click):**
* Simply double-click **`zenith.exe`** or **`zenith.bat`** in Windows Explorer!
* Or run in Command Prompt / PowerShell:
```cmd
zenith.exe
:: Or via PowerShell:
.\zenith-install.ps1
```

The bootstrapper automatically guides you through 8 polished stages:
`[1/8] Detecting system` → `[2/8] Checking Docker` → `[3/8] Installing dependencies` → `[4/8] Validating config` → `[5/8] Building containers` → `[6/8] Starting services` → `[7/8] Waiting for health checks` → `[8/8] Opening Zenith`.

---

### Option 2: Docker Compose Direct Launch

```bash
# 1. Clone repository
git clone https://github.com/Aditya-Gamer011/zenith.git
cd zenith

# 2. Initialize environment (.env.example has all defaults)
cp .env.example .env

# 3. Build and launch containers in detached mode
docker compose up --build -d
```
Open **`http://localhost:8005`** in your browser.

---

### Option 3: Native Python Virtual Environment (Development)

```bash
# 1. Clone or navigate to the repository
cd zenith

# 2. Create and activate a Python 3.11+ virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies and Playwright browser
pip install -r requirements.txt
playwright install chromium

# 4. Configure environment (Gemini API key is the only required secret!)
cp .env.example .env
# Edit .env and enter GEMINI_API_KEY=your_key_here

# 5. Launch Zenith
python run.py
```
Open **`http://localhost:8005`** in your browser.

---

## 🔒 First-Time Setup Wizard & Secrets Manager

When launching for the first time without credentials, Zenith greets you with an intuitive **First-Time Setup Wizard**:

1. **Only 1 Required Credential**:
   - **Google Gemini API Key**: The only key needed to activate Zenith's core intelligence.
   - Built-in **"Test Key"** button verifies credentials directly against Google AI Studio in real time before saving.
2. **Interactive Configuration Categories**:
   - 🧠 **AI Brain**: Gemini API Key, Gemini Live bidirectional audio streaming, DeepSeek/OpenAI fallback.
   - 👤 **Personal Profile**: Display name, email, timezone, and custom bio facts.
   - 🎙️ **Voice & Audio**: Groq Whisper STT, Edge neural TTS (natural voices across accents).
   - 🗺️ **Maps & Geospatial**: Google Maps API key, Cesium Ion token for God's Eye View 3D Globe.
   - ☁️ **Cloud & Developer**: GitHub PAT, Cloudflare token, Vercel deployments.
   - 🏠 **Homelab & Smart Home**: Home Assistant token & URL, Jellyfin API key.
   - 🛡️ **Sovereign Operating Layer**: Ghost Mode toggle, Clippy Vision, ActivityWatch, Mem0, and Camera toggles.
3. **Safe Hot-Reloading**:
   - Saves securely to `.env` while preserving comments, creates database records, and immediately reloads settings in-process. Access the secrets manager anytime by clicking your avatar in the header.

---

## 🧪 Automated Testing

Zenith includes an extensive test suite verifying ReAct orchestration, tool contracts, privacy guards, memory deduplication, and REST/WebSocket APIs:

```bash
# Run the complete test suite
.venv/bin/pytest -v
```

**Test Suite Status**: `103 passed, 0 failed`

---

## 📂 Repository Structure

```
zenith/
├── docs/                     # Full technical manuals & API reference
├── zenith/                   # Core Python application package
│   ├── core/                 # Orchestrator, prompts, config, provider, tools registry
│   ├── memory/               # SQLite persistent memory & knowledge graph
│   ├── services/             # Operating layer (Clippy, ActivityWatch, Mem0, Vision, Privacy)
│   ├── integrations/         # Figma & Canva OAuth bridges and design tools
│   ├── tools/                # 170+ domain tools (Browser, GitHub, Docker, Home Assistant)
│   └── voice/                # Groq Whisper STT, Edge TTS, Gemini Live streaming
├── static/                   # Glassmorphic frontend web UI, styles, shaders, and widgets
├── tests/                    # 103+ unit, integration, and contract tests
├── scripts/                  # Helper utilities (OAuth tokens, calendar auth)
├── gods-eye-view/            # 3D Earth observation satellite console
├── figma-plugin/             # Zenith Figma live design sync plugin
├── Dockerfile                # Production container specification
├── docker-compose.yml        # Multi-service local & production composition
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
├── run.py                    # Server launch entrypoint
└── .env.example              # Documented environment variable template
```

---

## 🛡️ License

Released under the [MIT License](LICENSE). Contributions, bug reports, and suggestions are warmly welcome!
