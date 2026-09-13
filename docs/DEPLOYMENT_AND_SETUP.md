# Zenith · Deployment & Getting Live Guide

This guide explains how to get Zenith running live, configure its environment, expose it securely to the internet, and maintain smooth 24/7 operations.

---

## 1. System Requirements

- **Operating System**: Linux (Ubuntu, Debian, Fedora, Arch, Raspberry Pi OS), macOS, or Windows (via WSL2).
- **Python**: Version `3.11` or higher.
- **Node.js** (optional): Not required at runtime; all frontend assets are vanilla CSS/JS.
- **Docker & Docker Compose** (optional but recommended for production homelabs).
- **RAM**: Minimum 1 GB; recommended 2 GB+.
- **Disk**: 500 MB for core installation + dependencies.

---

## 2. Launching Zenith Live

### Method A: Native Python Virtual Environment (Fastest)

```bash
# 1. Clone or navigate to the repository
cd zenith

# 2. Create and activate a Python 3.11+ virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install core dependencies
pip install -r requirements.txt

# 4. Copy the environment template
cp .env.example .env

# 5. Launch the Zenith server
python run.py
```

Zenith will start on **`http://localhost:8005`**.
Open this URL in your web browser. If no API keys are configured, Zenith automatically opens the **First-Time Setup Wizard** so you can enter your Google Gemini API key.

---

### Method B: Docker Compose (Recommended for Production)

Zenith includes a ready-to-run `docker-compose.yml` and `Dockerfile`:

```bash
cd zenith

# 1. Ensure .env exists (copy from .env.example if needed)
cp -n .env.example .env

# 2. Build and launch the container in detached mode
docker compose up --build -d

# 3. Verify the container is running and healthy
docker compose ps
docker compose logs -f
```

- **Exposed Port**: `8005:8005`
- **Container Name**: `zenith`
- **Volume Mounts**: Persists SQLite database files and outputs across container restarts.

---

## 3. Configuration & Environment Variables

Zenith requires only **one mandatory credential** to boot and operate:
- **`GEMINI_API_KEY`**: Obtain for free from [Google AI Studio](https://aistudio.google.com/apikey).

All other credentials are fully optional and unlock specialized capabilities:

| Variable | Service | What it Unlocks |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studio | **Required**. Core reasoning, tool orchestration, and chat intelligence. |
| `LIVE_VOICE_ENABLED` | Google Gemini Live | `yes` enables real-time bidirectional native audio voice streaming. |
| `GROQ_API_KEY` | Groq Console | Lightning-fast Whisper Large v3 voice transcription. |
| `FALLBACK_API_KEY` | DeepSeek / OpenAI | Secondary intelligence when primary API limits are reached. |
| `RESEND_API_KEY` | Resend | Outbound email delivery for generated reports, presentations, and alerts. |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Gmail IMAP | Inbound email monitoring and autonomous triage. |
| `GH_TOKEN` | GitHub | Pull request creation, AI code reviews, and repo inspection. |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console | Live map embeds, directions, commute estimation, and place searches. |
| `HOME_ASSISTANT_URL` / `_TOKEN` | Home Assistant | Direct smart home control over AC, fans, lights, soundbars, and plugs. |
| `ALLOW_SHELL` | Host System | `yes` enables host terminal command execution via the `shell` tool. |
| `ALLOW_DOCKER` | Docker Engine | `yes` enables container status monitoring and controlled restarts. |

> **Tip**: You don't need to manually edit `.env` for common keys! You can click the **User Profile** button on the top-left of the Zenith web interface to open the **Settings & Secrets** wizard and enter your credentials securely with live key verification.

---

## 4. Making Zenith Live to the World (Public & Mobile Access)

To access Zenith securely from your phone, laptop, or anywhere outside your local network, set up an encrypted tunnel:

### Option 1: Cloudflare Tunnel (`cloudflared`) — Zero Port Forwarding

Cloudflare Tunnels allow you to expose Zenith over HTTPS without opening ports on your home router.

1. Install `cloudflared` on your host machine:
   ```bash
   sudo apt-get install cloudflared
   ```
2. Authenticate and create a tunnel:
   ```bash
   cloudflared tunnel login
   cloudflared tunnel create zenith
   ```
3. Configure your tunnel ingress in `~/.cloudflared/config.yml`:
   ```yaml
   tunnel: <TUNNEL_UUID>
   credentials-file: /home/user/.cloudflared/<TUNNEL_UUID>.json

   ingress:
     - hostname: zenith.yourdomain.com
       service: http://localhost:8005
     - service: http_status:404
   ```
4. Route DNS and start the tunnel:
   ```bash
   cloudflared tunnel route dns zenith zenith.yourdomain.com
   cloudflared tunnel run zenith
   ```
5. Visit `https://zenith.yourdomain.com` from any device. WebSocket connections (`/ws` and `/ws/live`) work out-of-the-box over Cloudflare.

---

### Option 2: Caddy Reverse Proxy (Automatic Free Let's Encrypt SSL)

If you have a public IP or port forwarding (ports 80 & 443):

Add this block to your `/etc/caddy/Caddyfile`:

```caddy
zenith.yourdomain.com {
    reverse_proxy localhost:8005 {
        # WebSocket support is enabled by default in Caddy v2
    }
}
```

Reload Caddy:
```bash
sudo systemctl reload caddy
```

---

## 5. Running as a System Service (Systemd)

To ensure Zenith boots automatically when your server starts and restarts on any unexpected crash, create a systemd service:

1. Create `/etc/systemd/system/zenith.service`:
   ```ini
   [Unit]
   Description=Zenith Autonomous Command Engine
   After=network.target

   [Service]
   Type=simple
   User=user
   WorkingDirectory=/path/to/zenith
   EnvironmentFile=/path/to/zenith/.env
   ExecStart=/path/to/zenith/.venv/bin/python /path/to/zenith/run.py
   Restart=always
   RestartSec=5
   StandardOutput=journal
   StandardError=journal

   [Install]
   WantedBy=multi-user.target
   ```

2. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable zenith
   sudo systemctl start zenith
   ```

3. Check service status and logs:
   ```bash
   sudo systemctl status zenith
   journalctl -u zenith -f
   ```

---

## 6. Health Checks, Diagnostics & Self-Healing

- **HTTP Health Endpoint**:
  ```bash
  curl http://localhost:8005/api/health
  ```
  Returns `{"status": "ok", "version": "...", "uptime": ...}`.
- **Port In Use Error**:
  If port `8005` is occupied by another service:
  ```bash
  # Check what process is using port 8005
  lsof -i :8005
  # Or configure a different port in your .env:
  PORT=8010
  ```
- **Live Logs**:
  Zenith prints clear, human-readable startup logs indicating loaded tools, registered routes, and connection statuses.
