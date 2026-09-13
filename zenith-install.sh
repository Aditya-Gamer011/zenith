#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# ZENITH COGNITIVE OPERATING LAYER — UNIFIED BOOTSTRAPPER
# Single-command cross-platform installer & container orchestrator
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Aditya-Gamer011/zenith/main/zenith-install.sh | bash
#   OR: ./zenith-install.sh [options]
#
# Options:
#   --repair      Rebuild Docker images without cache, repair permissions & restart
#   --update      Pull latest repository commits, rebuild & restart
#   --uninstall   Gracefully stop services with confirmation to remove data
#   --stop        Stop Zenith services
#   --restart     Restart Zenith services
#   --logs        Stream live container logs
#   --status      Check system health & runtime status
#   -y, --yes     Non-interactive mode (auto-accept confirmations)
#   -h, --help    Show this help message
# ══════════════════════════════════════════════════════════════════════════════

set -eo pipefail

ZENITH_VERSION="2.1.0"
DEFAULT_PORT=8005
SYSTEM_PROFILE_DIR="$HOME/.zenith"
SYSTEM_PROFILE_FILE="$SYSTEM_PROFILE_DIR/system-info.json"
REPO_URL="https://github.com/Aditya-Gamer011/zenith.git"

# Text Styling
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    BOLD="\033[1m"
    DIM="\033[2m"
    CYAN="\033[0;36m"
    GREEN="\033[0;32m"
    YELLOW="\033[1;33m"
    RED="\033[0;31m"
    MAGENTA="\033[0;35m"
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    CYAN=""
    GREEN=""
    YELLOW=""
    RED=""
    MAGENTA=""
    RESET=""
fi

log_stage() {
    echo -e "\n${BOLD}${CYAN}$1${RESET}"
}

log_info() {
    echo -e "  ${DIM}ℹ${RESET}  $1"
}

log_ok() {
    echo -e "  ${GREEN}✔${RESET}  $1"
}

log_warn() {
    echo -e "  ${YELLOW}⚠️${RESET}  $1"
}

log_err() {
    echo -e "  ${RED}✖${RESET}  $1" >&2
}

prompt_confirm() {
    local prompt_msg="$1"
    local default_val="${2:-y}"

    if [ "${NON_INTERACTIVE:-0}" -eq 1 ]; then
        return 0
    fi

    local response
    if [ -e /dev/tty ]; then
        if [ "$default_val" = "y" ]; then
            printf "  ${BOLD}%s [Y/n]: ${RESET}" "$prompt_msg" > /dev/tty
        else
            printf "  ${BOLD}%s [y/N]: ${RESET}" "$prompt_msg" > /dev/tty
        fi
        read -r response < /dev/tty || response=""
    else
        response="$default_val"
    fi

    response="${response:-$default_val}"
    case "$response" in
        [yY][eE][sS]|[yY]) return 0 ;;
        *) return 1 ;;
    esac
}

print_banner() {
    echo -e "${BOLD}${CYAN}"
    echo "  ███████╗███████╗███╗   ██╗██╗████████╗██╗  ██╗"
    echo "  ╚══███╔╝██╔════╝████╗  ██║██║╚══██╔══╝██║  ██║"
    echo "    ███╔╝ █████╗  ██╔██╗ ██║██║   ██║   ███████║"
    echo "   ███╔╝  ██╔══╝  ██║╚██╗██║██║   ██║   ██╔══██║"
    echo "  ███████╗███████╗██║ ╚████║██║   ██║   ██║  ██║"
    echo "  ╚══════╝╚══════╝╚═╝  ╚═══╝╚═╝   ╚═╝   ╚═╝  ╚═╝"
    echo -e "${RESET}${DIM}  Autonomous AI Operating Layer • Production Bootstrapper v${ZENITH_VERSION}${RESET}\n"
}

# ──────────────────────────────────────────────────────────────────────────────
# COMMAND LINE ARGUMENT PARSING
# ──────────────────────────────────────────────────────────────────────────────
MODE="install"
NON_INTERACTIVE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --repair)
            MODE="repair"
            shift
            ;;
        --update)
            MODE="update"
            shift
            ;;
        --uninstall)
            MODE="uninstall"
            shift
            ;;
        --stop)
            MODE="stop"
            shift
            ;;
        --restart)
            MODE="restart"
            shift
            ;;
        --logs)
            MODE="logs"
            shift
            ;;
        --status)
            MODE="status"
            shift
            ;;
        -y|--yes|--non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        -h|--help)
            print_banner
            echo -e "Usage: ./zenith-install.sh [COMMAND | OPTION]"
            echo ""
            echo "Commands:"
            echo "  (no args)     Run full 8-stage Zenith installation and launcher"
            echo "  --repair      Rebuild Docker images without cache, repair volume permissions & restart"
            echo "  --update      Pull latest repository commits, rebuild container & restart"
            echo "  --uninstall   Safely stop containers and optionally remove persistent data"
            echo "  --stop        Stop Zenith background container"
            echo "  --restart     Restart Zenith background container"
            echo "  --logs        Stream live container logs (docker compose logs -f)"
            echo "  --status      Inspect healthcheck, port status & system profile"
            echo ""
            echo "Options:"
            echo "  -y, --yes     Auto-confirm all prompts (non-interactive mode)"
            echo "  -h, --help    Display this help message"
            echo ""
            exit 0
            ;;
        *)
            log_warn "Unknown argument: $1"
            shift
            ;;
    esac
done

# ──────────────────────────────────────────────────────────────────────────────
# LOCATE OR CLONE ZENITH WORKSPACE
# ──────────────────────────────────────────────────────────────────────────────
resolve_workspace() {
    if [ -f "run.py" ] && [ -d "zenith" ] && [ -f "Dockerfile" ]; then
        ZENITH_DIR="$(pwd)"
    elif [ -f "../run.py" ] && [ -d "../zenith" ] && [ -f "../Dockerfile" ]; then
        ZENITH_DIR="$(cd .. && pwd)"
    elif [ -d "$HOME/.zenith/app" ] && [ -f "$HOME/.zenith/app/run.py" ]; then
        ZENITH_DIR="$HOME/.zenith/app"
    else
        log_info "Zenith repository not detected in current directory."
        ZENITH_DIR="$HOME/.zenith/app"
        mkdir -p "$HOME/.zenith"
        if [ ! -d "$ZENITH_DIR" ]; then
            log_info "Cloning Zenith repository into $ZENITH_DIR..."
            if command -v git >/dev/null 2>&1; then
                git clone --depth 1 "$REPO_URL" "$ZENITH_DIR"
            else
                log_err "Git is required to clone Zenith repository. Please install git or run from the Zenith directory."
                exit 1
            fi
        fi
    fi
    cd "$ZENITH_DIR"
    log_info "Working directory: $ZENITH_DIR"
}

detect_system() {
    log_stage "[1/8] Detecting system..."

    OS_TYPE="$(uname -s)"
    ARCH="$(uname -m)"
    KERNEL="$(uname -r)"
    CURRENT_USER="$(whoami 2>/dev/null || id -un)"
    CURRENT_UID="$(id -u 2>/dev/null || echo 1000)"
    CURRENT_SHELL="$(basename "${SHELL:-bash}")"

    DISTRO_NAME="Unknown"
    DISTRO_ID="unknown"
    DISTRO_VERSION=""

    case "$OS_TYPE" in
        Linux)
            if [ -f /etc/os-release ]; then
                DISTRO_ID="$(grep -E '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"' || echo "linux")"
                DISTRO_NAME="$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '\"' || echo "Linux")"
                DISTRO_VERSION="$(grep -E '^VERSION_ID=' /etc/os-release | cut -d= -f2 | tr -d '\"' || echo "")"
            elif [ -f /etc/redhat-release ]; then
                DISTRO_NAME="$(cat /etc/redhat-release)"
                DISTRO_ID="rhel"
            else
                DISTRO_NAME="Generic Linux"
                DISTRO_ID="linux"
            fi
            ;;
        Darwin)
            DISTRO_ID="macos"
            DISTRO_NAME="macOS $(sw_vers -productVersion 2>/dev/null || echo "")"
            DISTRO_VERSION="$(sw_vers -productVersion 2>/dev/null || echo "")"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            DISTRO_ID="windows"
            DISTRO_NAME="Windows ($OS_TYPE)"
            ;;
        *)
            DISTRO_NAME="$OS_TYPE"
            ;;
    esac

    # Hardware metrics
    CPU_CORES=1
    if command -v nproc >/dev/null 2>&1; then
        CPU_CORES=$(nproc)
    elif command -v sysctl >/dev/null 2>&1; then
        CPU_CORES=$(sysctl -n hw.ncpu 2>/dev/null || echo 1)
    fi

    TOTAL_RAM_MB=0
    AVAIL_RAM_MB=0

    if [ -f /proc/meminfo ]; then
        TOTAL_RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
        AVAIL_RAM_KB=$(grep -E 'MemAvailable|MemFree' /proc/meminfo | head -n1 | awk '{print $2}')
        TOTAL_RAM_MB=$(( TOTAL_RAM_KB / 1024 ))
        AVAIL_RAM_MB=$(( AVAIL_RAM_KB / 1024 ))
    elif [ "$OS_TYPE" = "Darwin" ] && command -v sysctl >/dev/null 2>&1; then
        TOTAL_RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        TOTAL_RAM_MB=$(( TOTAL_RAM_BYTES / 1024 / 1024 ))
        AVAIL_RAM_MB=$(( TOTAL_RAM_MB / 2 ))
    fi
    TOTAL_RAM_GB=$(awk "BEGIN {printf \"%.1f\", $TOTAL_RAM_MB / 1024}")

    # GPU Introspection
    GPU_AVAILABLE=false
    GPU_TYPE="none"
    GPU_NAME="none"
    GPU_CUDA=false

    if command -v nvidia-smi >/dev/null 2>&1; then
        GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1 || echo "NVIDIA GPU")"
        GPU_AVAILABLE=true
        GPU_TYPE="nvidia"
        GPU_CUDA=true
    elif [ "$OS_TYPE" = "Darwin" ] && [[ "$ARCH" =~ ^(arm64|aarch64)$ ]]; then
        GPU_AVAILABLE=true
        GPU_TYPE="apple_silicon"
        GPU_NAME="Apple Silicon Metal GPU"
    elif command -v lspci >/dev/null 2>&1; then
        if lspci 2>/dev/null | grep -qiE 'vga|3d|display'; then
            GPU_AVAILABLE=true
            GPU_TYPE="discrete/integrated"
            GPU_NAME="$(lspci | grep -iE 'vga|3d|display' | head -n1 | cut -d: -f3- | sed -e 's/^[[:space:]]*//')"
        fi
    fi

    # Determine resource profile classification
    if [ "$TOTAL_RAM_MB" -lt 2048 ] && [ "$TOTAL_RAM_MB" -gt 0 ]; then
        MEMORY_CLASS="low"
        RECOMMENDED_WORKERS=1
    elif [ "$TOTAL_RAM_MB" -lt 8192 ] && [ "$TOTAL_RAM_MB" -gt 0 ]; then
        MEMORY_CLASS="standard"
        RECOMMENDED_WORKERS=2
    else
        MEMORY_CLASS="high"
        RECOMMENDED_WORKERS=4
    fi

    # Save profile to ~/.zenith/system-info.json (NEVER save API keys/secrets)
    mkdir -p "$SYSTEM_PROFILE_DIR"
    chmod 700 "$SYSTEM_PROFILE_DIR"

    TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date)"

    cat <<EOF > "$SYSTEM_PROFILE_FILE"
{
  "system": {
    "os_family": "$(echo "$OS_TYPE" | tr '[:upper:]' '[:lower:]')",
    "os_name": "$DISTRO_NAME",
    "distribution_id": "$DISTRO_ID",
    "distribution_version": "$DISTRO_VERSION",
    "kernel": "$KERNEL",
    "architecture": "$ARCH"
  },
  "hardware": {
    "cpu_cores": $CPU_CORES,
    "ram_total_mb": $TOTAL_RAM_MB,
    "ram_total_gb": "$TOTAL_RAM_GB",
    "ram_available_mb": $AVAIL_RAM_MB,
    "memory_class": "$MEMORY_CLASS",
    "gpu": {
      "available": $GPU_AVAILABLE,
      "type": "$GPU_TYPE",
      "name": "$GPU_NAME",
      "cuda": $GPU_CUDA
    }
  },
  "user": {
    "username": "$CURRENT_USER",
    "uid": $CURRENT_UID,
    "shell": "$CURRENT_SHELL"
  },
  "runtime_adaptation": {
    "recommended_workers": $RECOMMENDED_WORKERS,
    "default_port": $DEFAULT_PORT,
    "zenith_version": "$ZENITH_VERSION",
    "generated_at": "$TIMESTAMP"
  }
}
EOF
    chmod 600 "$SYSTEM_PROFILE_FILE"

    log_ok "Platform: ${BOLD}$DISTRO_NAME${RESET} ($ARCH, Kernel $KERNEL)"
    log_ok "Resources: ${BOLD}${CPU_CORES} cores${RESET}, ${BOLD}${TOTAL_RAM_GB} GB RAM${RESET} (Class: $MEMORY_CLASS)"
    if [ "$GPU_AVAILABLE" = true ]; then
        log_ok "Acceleration: ${BOLD}$GPU_NAME${RESET}"
    else
        log_info "GPU: Software rendering (CPU)"
    fi
    log_ok "Profile saved: ${BOLD}$SYSTEM_PROFILE_FILE${RESET} (Zero secrets stored)"
}

# ──────────────────────────────────────────────────────────────────────────────
# QUICK MODES: STOP, RESTART, LOGS, STATUS, UNINSTALL
# ──────────────────────────────────────────────────────────────────────────────
run_quick_mode() {
    resolve_workspace

    case "$MODE" in
        stop)
            print_banner
            log_stage "Stopping Zenith services..."
            docker compose down
            log_ok "Zenith services stopped."
            exit 0
            ;;
        restart)
            print_banner
            log_stage "Restarting Zenith services..."
            docker compose restart
            log_ok "Zenith restarted."
            exit 0
            ;;
        logs)
            docker compose logs -f
            exit 0
            ;;
        status)
            print_banner
            log_stage "Zenith System & Container Status"
            if [ ! -f "$SYSTEM_PROFILE_FILE" ]; then
                detect_system
            fi
            if [ -f "$SYSTEM_PROFILE_FILE" ]; then
                echo -e "${DIM}Host Profile (${SYSTEM_PROFILE_FILE}):${RESET}"
                cat "$SYSTEM_PROFILE_FILE"
                echo ""
            fi
            echo -e "${DIM}Containers:${RESET}"
            docker compose ps
            echo ""
            echo -e "${DIM}Healthcheck (/api/health):${RESET}"
            if curl -fsSL "http://localhost:${ZENITH_PORT:-8005}/api/health" 2>/dev/null; then
                echo ""
                log_ok "Zenith is online and responding."
            else
                log_warn "Zenith is not responding on http://localhost:${ZENITH_PORT:-8005}"
            fi
            exit 0
            ;;
        uninstall)
            print_banner
            log_stage "Zenith Safe Uninstaller"
            echo -e "${YELLOW}This will stop and remove Zenith containers.${RESET}"
            if prompt_confirm "Stop Zenith containers and network?" "y"; then
                docker compose down
                log_ok "Containers stopped."
            fi

            if prompt_confirm "Do you also want to remove persistent volumes (user memory, data, documents)?" "n"; then
                docker compose down -v
                log_warn "Persistent volumes removed."
            else
                log_ok "Persistent volumes preserved."
            fi

            if prompt_confirm "Remove local system profile ($SYSTEM_PROFILE_DIR)?" "n"; then
                rm -rf "$SYSTEM_PROFILE_DIR"
                log_ok "Profile directory removed."
            fi
            log_ok "Uninstall completed safely."
            exit 0
            ;;
    esac
}

if [[ "$MODE" =~ ^(stop|restart|logs|status|uninstall)$ ]]; then
    run_quick_mode
fi

# ──────────────────────────────────────────────────────────────────────────────
# FULL 8-STAGE BOOTSTRAP WORKFLOW
# ──────────────────────────────────────────────────────────────────────────────
print_banner
resolve_workspace

detect_system

# ── STAGE 2: CHECKING DOCKER ──────────────────────────────────────────────────
log_stage "[2/8] Checking Docker..."

DOCKER_CMD="docker"
INSTALL_DOCKER=0

if ! command -v docker >/dev/null 2>&1; then
    INSTALL_DOCKER=1
fi

if [ "$INSTALL_DOCKER" -eq 1 ]; then
    log_warn "Docker is not installed on this host."
    echo -e "  Zenith requires Docker Engine to provide isolated, reproducible, non-root execution."

    if ! prompt_confirm "Install official Docker packages for $DISTRO_NAME now?" "y"; then
        log_err "Docker installation declined. Zenith cannot boot without a container engine."
        exit 1
    fi

    log_info "Initiating official Docker installation for $DISTRO_ID..."

    SUDO_CMD=""
    if [ "$CURRENT_UID" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO_CMD="sudo"
        else
            log_err "Elevated privileges (sudo) are required to install Docker packages."
            exit 1
        fi
    fi

    case "$DISTRO_ID" in
        ubuntu|debian|pop|mint|raspbian)
            log_info "Running official Docker convenience installer (get.docker.com)..."
            curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
            $SUDO_CMD sh /tmp/get-docker.sh
            rm -f /tmp/get-docker.sh
            ;;
        fedora|rhel|centos|rocky|alma)
            log_info "Installing Docker via package manager..."
            $SUDO_CMD dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin || \
            $SUDO_CMD dnf install -y docker docker-compose
            ;;
        arch|manjaro)
            log_info "Installing Docker via pacman..."
            $SUDO_CMD pacman -Sy --noconfirm docker docker-compose
            ;;
        alpine)
            log_info "Installing Docker via apk..."
            $SUDO_CMD apk add docker docker-cli-compose
            ;;
        macos)
            log_warn "On macOS, Docker Desktop is recommended."
            if command -v brew >/dev/null 2>&1; then
                log_info "Installing Docker Desktop via Homebrew..."
                brew install --cask docker
                open -a Docker || true
            else
                log_err "Homebrew not found. Please install Docker Desktop from https://www.docker.com/products/docker-desktop/"
                exit 1
            fi
            ;;
        *)
            log_info "Attempting official Docker script for $DISTRO_ID..."
            curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
            $SUDO_CMD sh /tmp/get-docker.sh
            rm -f /tmp/get-docker.sh
            ;;
    esac

    # Start and enable Docker service on Linux
    if [ "$OS_TYPE" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
        log_info "Enabling and starting Docker service..."
        $SUDO_CMD systemctl enable --now docker || true
    elif [ "$OS_TYPE" = "Linux" ] && command -v service >/dev/null 2>&1; then
        $SUDO_CMD service docker start || true
    fi

    # Add current user to docker group
    if [ "$CURRENT_UID" -ne 0 ] && [ "$OS_TYPE" = "Linux" ]; then
        if getent group docker >/dev/null 2>&1; then
            log_info "Granting $CURRENT_USER permission to execute Docker commands..."
            $SUDO_CMD usermod -aG docker "$CURRENT_USER" || true
        fi
    fi
fi

# Verify Docker daemon is actively responding
DOCKER_READY=false
if docker info >/dev/null 2>&1; then
    DOCKER_READY=true
elif sudo docker info >/dev/null 2>&1; then
    DOCKER_READY=true
    DOCKER_CMD="sudo docker"
    log_info "Using elevated docker command for current session."
fi

if [ "$DOCKER_READY" != true ]; then
    # Try starting daemon if stopped
    if [ "$OS_TYPE" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
        log_info "Starting Docker systemd daemon..."
        sudo systemctl start docker || true
        sleep 2
        if docker info >/dev/null 2>&1; then
            DOCKER_READY=true
        fi
    fi
fi

if [ "$DOCKER_READY" != true ]; then
    log_err "Docker daemon is not running or current user lacks permissions."
    echo -e "  To fix permissions: ${BOLD}sudo usermod -aG docker $CURRENT_USER && newgrp docker${RESET}"
    echo -e "  To start daemon:     ${BOLD}sudo systemctl start docker${RESET}"
    exit 1
fi

DOCKER_VERSION="$($DOCKER_CMD --version | cut -d, -f1)"
log_ok "$DOCKER_VERSION active and responsive"

# ── STAGE 3: INSTALLING MISSING DEPENDENCIES ──────────────────────────────────
log_stage "[3/8] Installing missing dependencies..."

COMPOSE_CMD=""
if $DOCKER_CMD compose version >/dev/null 2>&1; then
    COMPOSE_CMD="$DOCKER_CMD compose"
    COMPOSE_VER="$($DOCKER_CMD compose version --short 2>/dev/null || echo "v2")"
    log_ok "Docker Compose plugin ($COMPOSE_VER) detected"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
    COMPOSE_VER="$(docker-compose --version)"
    log_ok "Standalone docker-compose ($COMPOSE_VER) detected"
else
    log_warn "Docker Compose is not available. Installing official Compose plugin..."
    DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
    mkdir -p "$DOCKER_CONFIG/cli-plugins"
    COMPOSE_ARCH="$ARCH"
    case "$ARCH" in
        x86_64) COMPOSE_ARCH="x86_64" ;;
        aarch64|arm64) COMPOSE_ARCH="aarch64" ;;
        *) COMPOSE_ARCH="x86_64" ;;
    esac
    LATEST_COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$COMPOSE_ARCH"
    if curl -sSL "$LATEST_COMPOSE_URL" -o "$DOCKER_CONFIG/cli-plugins/docker-compose"; then
        chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose"
        COMPOSE_CMD="$DOCKER_CMD compose"
        log_ok "Docker Compose plugin installed to user CLI plugins."
    else
        log_err "Failed to download Docker Compose plugin. Please install docker-compose-plugin."
        exit 1
    fi
fi

# ── STAGE 4: VALIDATING ZENITH CONFIGURATION ──────────────────────────────────
log_stage "[4/8] Validating Zenith configuration..."

# 1. Disk Space check (at least 2GB free)
FREE_DISK_MB=0
if command -v df >/dev/null 2>&1; then
    FREE_DISK_KB=$(df -k . | awk 'NR==2 {print $4}')
    FREE_DISK_MB=$(( FREE_DISK_KB / 1024 ))
    FREE_DISK_GB=$(awk "BEGIN {printf \"%.1f\", $FREE_DISK_MB / 1024}")
    if [ "$FREE_DISK_MB" -lt 2000 ]; then
        log_warn "Low disk space: only ${FREE_DISK_GB} GB available. 2+ GB recommended."
    else
        log_ok "Disk space: ${FREE_DISK_GB} GB available"
    fi
fi

# 2. Directory structure check
mkdir -p data data/memory static/screenshots /tmp/zenith-files 2>/dev/null || true
log_ok "Directory structure verified"

# 3. Port check (8005)
TARGET_PORT="${ZENITH_PORT:-$DEFAULT_PORT}"
PORT_OCCUPIED=false

if command -v lsof >/dev/null 2>&1; then
    if lsof -i :"$TARGET_PORT" >/dev/null 2>&1; then
        PORT_OCCUPIED=true
    fi
elif command -v ss >/dev/null 2>&1; then
    if ss -tuln | grep -q ":$TARGET_PORT "; then
        PORT_OCCUPIED=true
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln | grep -q ":$TARGET_PORT "; then
        PORT_OCCUPIED=true
    fi
fi

if [ "$PORT_OCCUPIED" = true ]; then
    # Test if it's already Zenith running
    if curl -fsSL "http://localhost:$TARGET_PORT/api/health" >/dev/null 2>&1; then
        log_ok "Port $TARGET_PORT is already hosting an active Zenith instance."
    else
        log_warn "Port $TARGET_PORT is currently occupied by another host process."
        log_info "You can configure a different port by setting ZENITH_PORT in .env"
    fi
else
    log_ok "Port $TARGET_PORT is available"
fi

# 4. Environment (.env) merge & validation
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        log_ok "Created initial .env configuration from .env.example"
    else
        touch .env
        log_info "Created blank .env configuration file"
    fi
else
    # Merge missing keys from .env.example without overwriting existing user values
    if [ -f ".env.example" ]; then
        MERGED_COUNT=0
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip comments and empty lines
            if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "${line// }" ]]; then
                continue
            fi
            KEY="$(echo "$line" | cut -d= -f1 | tr -d ' ')"
            if [ -n "$KEY" ] && ! grep -q "^[[:space:]]*$KEY=" .env; then
                echo "$line" >> .env
                MERGED_COUNT=$(( MERGED_COUNT + 1 ))
            fi
        done < .env.example
        if [ "$MERGED_COUNT" -gt 0 ]; then
            log_ok "Updated .env: merged $MERGED_COUNT new configuration keys (existing values preserved)"
        else
            log_ok ".env configuration verified (all keys up to date)"
        fi
    fi
fi

# Check GEMINI_API_KEY without ever printing secrets to terminal
GEMINI_CONFIGURED=false
if grep -q "^[[:space:]]*GEMINI_API_KEY=" .env 2>/dev/null; then
    KEY_VAL="$(grep "^[[:space:]]*GEMINI_API_KEY=" .env | cut -d= -f2- | tr -d '\"' | tr -d "'" | tr -d ' ')"
    if [ -n "$KEY_VAL" ] && [ "$KEY_VAL" != "your_api_key_here" ]; then
        GEMINI_CONFIGURED=true
    fi
fi

if [ "$GEMINI_CONFIGURED" = true ]; then
    log_ok "AI Studio key: Configured in .env"
else
    log_warn "AI Studio key: Not configured in .env"
    log_info "Zenith will start in Setup Mode. You can paste your Gemini key in the web onboarding UI."
fi

# ── STAGE 5: BUILDING CONTAINERS ──────────────────────────────────────────────
log_stage "[5/8] Building containers..."

IMAGE_EXISTS=false
if $DOCKER_CMD image inspect zenith:latest >/dev/null 2>&1; then
    IMAGE_EXISTS=true
fi

if [ "$MODE" = "update" ]; then
    log_info "Pulling latest repository updates..."
    git pull --rebase || true
fi

if [ "$IMAGE_EXISTS" = true ] && [ "$MODE" != "repair" ] && [ "$MODE" != "update" ]; then
    log_ok "Reusing existing production image zenith:latest (run with --repair to force rebuild)"
else
    BUILD_FLAGS=""
    if [ "$MODE" = "repair" ]; then
        BUILD_FLAGS="--no-cache"
        log_info "Repair mode: rebuilding container with --no-cache..."
    else
        log_info "Building production container image..."
    fi
    $COMPOSE_CMD build $BUILD_FLAGS
    log_ok "Container build completed successfully"
fi

# ── STAGE 6: STARTING SERVICES ────────────────────────────────────────────────
log_stage "[6/8] Starting services..."

IS_RUNNING=false
if [ "$($COMPOSE_CMD ps -q zenith 2>/dev/null)" ]; then
    IS_RUNNING=true
fi

if [ "$IS_RUNNING" = true ] && [ "$MODE" != "repair" ] && [ "$MODE" != "update" ]; then
    log_ok "Zenith container (zenith-core) is already running"
else
    log_info "Starting Zenith containers in detached mode..."
    $COMPOSE_CMD up -d
    log_ok "Container zenith-core started in background"
fi

# ── STAGE 7: WAITING FOR HEALTH CHECKS ────────────────────────────────────────
log_stage "[7/8] Waiting for health checks..."

TARGET_URL="http://localhost:$TARGET_PORT"
HEALTH_URL="$TARGET_URL/api/health"
MAX_ATTEMPTS=40
ATTEMPT=1
IS_HEALTHY=false

echo -n "  "
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -fsSL "$HEALTH_URL" >/dev/null 2>&1; then
        IS_HEALTHY=true
        break
    fi
    echo -n "•"
    sleep 1.5
    ATTEMPT=$(( ATTEMPT + 1 ))
done
echo ""

if [ "$IS_HEALTHY" = true ]; then
    log_ok "Healthcheck verified: Zenith is online and responsive!"
else
    log_err "Zenith did not report healthy within $(( MAX_ATTEMPTS * 2 ))s."
    echo -e "\n${DIM}Recent Container Diagnostic Logs:${RESET}"
    $COMPOSE_CMD logs --tail=25 || true
    echo -e "\n${YELLOW}Troubleshooting:${RESET}"
    echo "  1. Check full logs:    ${BOLD}docker compose logs -f${RESET}"
    echo "  2. Try repair build:   ${BOLD}./zenith-install.sh --repair${RESET}"
    echo "  3. Verify port 8005:   ${BOLD}curl -v http://localhost:8005/api/health${RESET}"
    exit 1
fi

# ── STAGE 8: OPENING ZENITH ───────────────────────────────────────────────────
log_stage "[8/8] Opening Zenith..."

BROWSER_LAUNCHED=false

if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] || [ "$OS_TYPE" = "Darwin" ]; then
    if [ "$OS_TYPE" = "Darwin" ] && command -v open >/dev/null 2>&1; then
        open "$TARGET_URL" 2>/dev/null && BROWSER_LAUNCHED=true || true
    elif command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$TARGET_URL" 2>/dev/null && BROWSER_LAUNCHED=true || true
    elif command -v wslview >/dev/null 2>&1; then
        wslview "$TARGET_URL" 2>/dev/null && BROWSER_LAUNCHED=true || true
    fi
fi

if [ "$BROWSER_LAUNCHED" = true ]; then
    log_ok "Browser window launched to $TARGET_URL"
else
    log_info "Headless or terminal-only environment detected (browser not launched automatically)"
fi

# ── FINAL OPERATIONAL SUMMARY ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${GREEN}║                                                                          ║${RESET}"
echo -e "${BOLD}${GREEN}║                   ✦  ZENITH IS READY & OPERATIONAL  ✦                   ║${RESET}"
echo -e "${BOLD}${GREEN}║                                                                          ║${RESET}"
echo -e "${BOLD}${GREEN}║   Web Interface:     ${CYAN}${BOLD}${TARGET_URL}${GREEN}                               ║${RESET}"
echo -e "${BOLD}${GREEN}║   Container:         zenith-core                                         ║${RESET}"
echo -e "${BOLD}${GREEN}║   Status:            Healthy (HTTP 200 OK)                               ║${RESET}"
echo -e "${BOLD}${GREEN}║   System Profile:    ~/.zenith/system-info.json                          ║${RESET}"
echo -e "${BOLD}${GREEN}║                                                                          ║${RESET}"
echo -e "${BOLD}${GREEN}║   Useful Commands:                                                       ║${RESET}"
echo -e "${BOLD}${GREEN}║     Stream live logs:   ${BOLD}docker compose logs -f${RESET}${GREEN}                           ║${RESET}"
echo -e "${BOLD}${GREEN}║     Stop Zenith:        ${BOLD}docker compose down${RESET}${GREEN}                              ║${RESET}"
echo -e "${BOLD}${GREEN}║     Restart Zenith:     ${BOLD}docker compose restart${RESET}${GREEN}                           ║${RESET}"
echo -e "${BOLD}${GREEN}║     Update version:     ${BOLD}./zenith-install.sh --update${RESET}${GREEN}                     ║${RESET}"
echo -e "${BOLD}${GREEN}║     Repair stack:       ${BOLD}./zenith-install.sh --repair${RESET}${GREEN}                     ║${RESET}"
echo -e "${BOLD}${GREEN}║                                                                          ║${RESET}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════════════════╝${RESET}"
echo ""
