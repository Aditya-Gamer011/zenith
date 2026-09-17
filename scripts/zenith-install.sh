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
TARGET_PORT=$DEFAULT_PORT
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
    RESET="\033[0m"
else
    BOLD=""
    DIM=""
    CYAN=""
    GREEN=""
    YELLOW=""
    RED=""
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

    local response=""
    if [ -t 0 ]; then
        if [ "$default_val" = "y" ]; then
            printf "  ${BOLD}%s [Y/n]: ${RESET}" "$prompt_msg"
        else
            printf "  ${BOLD}%s [y/N]: ${RESET}" "$prompt_msg"
        fi
        read -r response || response=""
    elif (exec < /dev/tty) 2>/dev/null; then
        if [ "$default_val" = "y" ]; then
            printf "  ${BOLD}%s [Y/n]: ${RESET}" "$prompt_msg" > /dev/tty 2>/dev/null || true
        else
            printf "  ${BOLD}%s [y/N]: ${RESET}" "$prompt_msg" > /dev/tty 2>/dev/null || true
        fi
        read -r response < /dev/tty 2>/dev/null || response=""
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
        --repair|repair)
            MODE="repair"
            shift
            ;;
        --update|update)
            MODE="update"
            shift
            ;;
        --uninstall|uninstall)
            MODE="uninstall"
            shift
            ;;
        --stop|stop)
            MODE="stop"
            shift
            ;;
        --restart|restart)
            MODE="restart"
            shift
            ;;
        --logs|logs)
            MODE="logs"
            shift
            ;;
        --status|status)
            MODE="status"
            shift
            ;;
        start|--start)
            MODE="install"
            shift
            ;;
        -y|--yes|--non-interactive)
            NON_INTERACTIVE=1
            shift
            ;;
        -h|--help|help)
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
# AUTO-INSTALL PREREQUISITES & ARCHIVE RETRIEVAL (STANDALONE SUPPORT)
# ──────────────────────────────────────────────────────────────────────────────
ensure_git_installed() {
    if command -v git >/dev/null 2>&1; then
        return 0
    fi
    log_info "Git is not detected. Attempting automatic installation via system package manager..."
    local SUDO=""
    if [ "$(id -u 2>/dev/null || echo 1000)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update -qq >/dev/null 2>&1 || true
        $SUDO apt-get install -y -qq git >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then
        $SUDO dnf install -y -q git >/dev/null 2>&1 || true
    elif command -v yum >/dev/null 2>&1; then
        $SUDO yum install -y -q git >/dev/null 2>&1 || true
    elif command -v pacman >/dev/null 2>&1; then
        $SUDO pacman -Sy --noconfirm git >/dev/null 2>&1 || true
    elif command -v apk >/dev/null 2>&1; then
        $SUDO apk add --no-cache git >/dev/null 2>&1 || true
    elif command -v zypper >/dev/null 2>&1; then
        $SUDO zypper --non-interactive install git >/dev/null 2>&1 || true
    elif command -v brew >/dev/null 2>&1; then
        brew install git >/dev/null 2>&1 || true
    fi

    if command -v git >/dev/null 2>&1; then
        log_ok "Git installed successfully."
        return 0
    fi
    return 1
}

retrieve_repo_archive() {
    local target_dir="$1"
    mkdir -p "$target_dir"
    log_info "Downloading Zenith repository archive directly from GitHub..."
    local archive_url="https://github.com/Aditya-Gamer011/zenith/archive/refs/heads/main.tar.gz"

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$archive_url" | tar -xzf - --strip-components=1 -C "$target_dir" 2>/dev/null || return 1
        return 0
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$archive_url" | tar -xzf - --strip-components=1 -C "$target_dir" 2>/dev/null || return 1
        return 0
    fi
    return 1
}

ensure_python_installed() {
    if command -v python3 >/dev/null 2>&1; then
        if python3 -c "import venv" >/dev/null 2>&1; then
            return 0
        fi
    fi
    log_info "Python 3 environment or venv module not detected. Attempting automatic installation..."
    local SUDO=""
    if [ "$(id -u 2>/dev/null || echo 1000)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    fi

    if command -v apt-get >/dev/null 2>&1; then
        $SUDO apt-get update -qq >/dev/null 2>&1 || true
        $SUDO apt-get install -y -qq python3 python3-pip python3-venv python3-dev >/dev/null 2>&1 || true
    elif command -v dnf >/dev/null 2>&1; then
        $SUDO dnf install -y -q python3 python3-pip python3-devel >/dev/null 2>&1 || true
    elif command -v yum >/dev/null 2>&1; then
        $SUDO yum install -y -q python3 python3-pip python3-devel >/dev/null 2>&1 || true
    elif command -v pacman >/dev/null 2>&1; then
        $SUDO pacman -Sy --noconfirm python python-pip >/dev/null 2>&1 || true
    elif command -v apk >/dev/null 2>&1; then
        $SUDO apk add --no-cache python3 py3-pip python3-dev >/dev/null 2>&1 || true
    elif command -v zypper >/dev/null 2>&1; then
        $SUDO zypper --non-interactive install python3 python3-pip python3-devel >/dev/null 2>&1 || true
    elif command -v brew >/dev/null 2>&1; then
        brew install python@3.12 >/dev/null 2>&1 || true
    fi

    if command -v python3 >/dev/null 2>&1; then
        log_ok "Python 3 environment configured."
        return 0
    elif command -v python >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

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
        if [ ! -f "$ZENITH_DIR/run.py" ]; then
            if [ -d "$ZENITH_DIR" ]; then
                rm -rf "$ZENITH_DIR"
            fi
            mkdir -p "$ZENITH_DIR"
            local retrieved=false
            if ensure_git_installed; then
                log_info "Cloning Zenith repository into $ZENITH_DIR..."
                if git clone --depth 1 "$REPO_URL" "$ZENITH_DIR" 2>/dev/null; then
                    retrieved=true
                fi
            fi
            if [ "$retrieved" != true ]; then
                log_info "Git clone unavailable or failed; retrieving Zenith repository archive directly..."
                if retrieve_repo_archive "$ZENITH_DIR"; then
                    retrieved=true
                fi
            fi
            if [ "$retrieved" != true ] || [ ! -f "$ZENITH_DIR/run.py" ]; then
                log_err "Failed to retrieve Zenith repository. Please install git or curl, or download Zenith manually."
                exit 1
            fi
            log_ok "Zenith repository successfully acquired."
        fi
    fi
    cd "$ZENITH_DIR"
    log_info "Working directory: $ZENITH_DIR"
}

load_target_port() {
    if [ -z "${ZENITH_PORT:-}" ] && [ -f ".env" ]; then
        local env_port
        env_port="$(grep -E '^[[:space:]]*ZENITH_PORT[[:space:]]*=' .env 2>/dev/null | tail -n1 | cut -d= -f2- | cut -d# -f1 | tr -d '\"'\'' ' || true)"
        if [ -n "$env_port" ]; then
            ZENITH_PORT="$env_port"
        fi
    fi
    TARGET_PORT="${ZENITH_PORT:-$DEFAULT_PORT}"
}

resolve_docker_and_compose() {
    DOCKER_CMD="docker"
    CURRENT_UID="$(id -u 2>/dev/null || echo 1000)"
    SUDO_CMD=""
    if [ "$CURRENT_UID" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    fi

    if docker info >/dev/null 2>&1; then
        DOCKER_CMD="docker"
    elif [ -n "$SUDO_CMD" ] && $SUDO_CMD docker info >/dev/null 2>&1; then
        DOCKER_CMD="$SUDO_CMD docker"
    fi

    COMPOSE_CMD=""
    if $DOCKER_CMD compose version >/dev/null 2>&1; then
        COMPOSE_CMD="$DOCKER_CMD compose"
    elif command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    elif [ -n "$SUDO_CMD" ] && $SUDO_CMD command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD="$SUDO_CMD docker-compose"
    else
        COMPOSE_CMD="$DOCKER_CMD compose"
    fi
}

start_docker_engine() {
    log_info "Attempting automatic Docker daemon ignition..."
    if [ "${OS_TYPE:-}" = "Darwin" ]; then
        if [ -d "/Applications/Docker.app" ] || command -v open >/dev/null 2>&1; then
            open -a Docker >/dev/null 2>&1 || true
        fi
    elif [ "${OS_TYPE:-}" = "Linux" ]; then
        if [ -n "${SUDO_CMD:-}" ]; then
            if command -v systemctl >/dev/null 2>&1; then
                $SUDO_CMD systemctl start docker >/dev/null 2>&1 || true
            elif command -v service >/dev/null 2>&1; then
                $SUDO_CMD service docker start >/dev/null 2>&1 || true
            fi
        else
            if command -v systemctl >/dev/null 2>&1; then
                systemctl start docker >/dev/null 2>&1 || true
            elif command -v service >/dev/null 2>&1; then
                service docker start >/dev/null 2>&1 || true
            fi
        fi
    fi

    printf "  Waiting for Docker engine to respond"
    local i=1
    while [ "$i" -le 20 ]; do
        printf "•"
        if docker info >/dev/null 2>&1; then
            printf "\n"
            DOCKER_CMD="docker"
            log_ok "Docker engine is online and responding."
            return 0
        elif [ -n "${SUDO_CMD:-}" ] && $SUDO_CMD docker info >/dev/null 2>&1; then
            printf "\n"
            DOCKER_CMD="$SUDO_CMD docker"
            log_ok "Docker engine is online (elevated) and responding."
            return 0
        fi
        sleep 1.5
        i=$(( i + 1 ))
    done
    printf "\n"
    return 1
}

start_native_engine() {
    local reason="${1:-Container engine unavailable}"
    log_warn "$reason"
    log_stage "[Native Engine] Activating Zenith Native Host Mode..."

    if [ -z "${OS_TYPE:-}" ]; then
        OS_TYPE="$(uname -s)"
    fi
    if [ -z "${IS_WSL:-}" ]; then
        IS_WSL=false
        if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
            IS_WSL=true
        fi
    fi

    local root_venv="$ZENITH_DIR/.venv"
    local root_py="$root_venv/bin/python"
    local root_pip="$root_venv/bin/pip"

    if [ ! -f "$root_py" ]; then
        if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
            ensure_python_installed || true
        fi
        log_info "Bootstrapping Python virtual environment in .venv..."
        if command -v python3 >/dev/null 2>&1; then
            python3 -m venv "$root_venv" || {
                log_info "Retrying Python venv bootstrapping after ensuring packages..."
                ensure_python_installed || true
                python3 -m venv "$root_venv" || {
                    log_err "Failed to create Python virtual environment with python3."
                    exit 1
                }
            }
        elif command -v python >/dev/null 2>&1; then
            python -m venv "$root_venv" || {
                ensure_python_installed || true
                python -m venv "$root_venv" || {
                    log_err "Failed to create Python virtual environment with python."
                    exit 1
                }
            }
        else
            log_err "Python is required for Zenith Native Host Mode. Please install python3."
            exit 1
        fi
    fi

    if [ -f "$ZENITH_DIR/requirements.txt" ]; then
        if ! "$root_py" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
            log_info "Installing Zenith dependencies into .venv..."
            "$root_pip" install -q -r "$ZENITH_DIR/requirements.txt"
        fi
    fi

    mkdir -p "$ZENITH_DIR/data"
    local native_pid_file="$ZENITH_DIR/data/zenith-native.pid"
    local native_log_file="$ZENITH_DIR/data/zenith-native.log"

    if [ -f "$native_pid_file" ]; then
        local old_pid
        old_pid="$(cat "$native_pid_file" 2>/dev/null || true)"
        if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
            kill "$old_pid" 2>/dev/null || true
        fi
        rm -f "$native_pid_file"
    fi

    if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
        log_info "Configuring Antigravity Coding Worker (agy)..."
        "$ZENITH_DIR/scripts/setup-worker.sh" install-and-start || log_warn "Antigravity worker startup notice"
    fi

    load_target_port
    log_info "Starting Zenith Cognitive Operating Layer via run.py on port $TARGET_PORT..."
    (cd "$ZENITH_DIR" && nohup "$root_py" run.py > "$native_log_file" 2>&1 & echo $! > "$native_pid_file")
    local new_pid
    new_pid="$(cat "$native_pid_file" 2>/dev/null || true)"
    log_ok "Zenith Native Engine started (PID $new_pid)"

    log_stage "Waiting for health checks..."
    local ready=false
    local target_url="http://localhost:$TARGET_PORT"
    local health_url="$target_url/api/health"
    local attempt=1
    printf "  "
    while [ "$attempt" -le 30 ]; do
        sleep 1.2
        printf "•"
        if curl -fsSL "$health_url" 2>/dev/null | grep -qiE '"status"[[:space:]]*:[[:space:]]*"ok"|Zenith'; then
            ready=true
            break
        fi
        attempt=$(( attempt + 1 ))
    done
    printf "\n"

    if [ -f "$ZENITH_DIR/scripts/create-desktop-shortcut.sh" ]; then
        bash "$ZENITH_DIR/scripts/create-desktop-shortcut.sh" >/dev/null 2>&1 || true
    fi

    if [ "$ready" = true ]; then
        log_ok "Healthcheck verified: Zenith is online at $target_url"
        if [ "$IS_WSL" = true ]; then
            if command -v wslview >/dev/null 2>&1; then
                wslview "$target_url" >/dev/null 2>&1 || true
            elif command -v cmd.exe >/dev/null 2>&1; then
                cmd.exe /c start "$target_url" >/dev/null 2>&1 || true
            fi
        elif [ "$OS_TYPE" = "Darwin" ]; then
            if command -v open >/dev/null 2>&1; then
                open "$target_url" >/dev/null 2>&1 || true
            fi
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "$target_url" >/dev/null 2>&1 || true
        fi
        exit 0
    else
        log_err "Zenith Native Engine did not respond in time. Check $native_log_file"
        exit 1
    fi
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
                DISTRO_ID="$(grep -E '^ID=' /etc/os-release | cut -d= -f2 | tr -d '\"' | tr -d "'" || echo "linux")"
                DISTRO_NAME="$(grep -E '^PRETTY_NAME=' /etc/os-release | cut -d= -f2 | tr -d '\"' | tr -d "'" || echo "Linux")"
                DISTRO_VERSION="$(grep -E '^VERSION_ID=' /etc/os-release | cut -d= -f2 | tr -d '\"' | tr -d "'" || echo "")"
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
    DISTRO_ID="$(echo "$DISTRO_ID" | tr '[:upper:]' '[:lower:]')"

    # Check for WSL environment
    IS_WSL=false
    if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null || [ -n "${WSL_DISTRO_NAME:-}" ]; then
        IS_WSL=true
        DISTRO_NAME="WSL2 ($DISTRO_NAME)"
    fi

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
        TOTAL_RAM_MB=$(( ${TOTAL_RAM_KB:-0} / 1024 ))
        AVAIL_RAM_MB=$(( ${AVAIL_RAM_KB:-0} / 1024 ))
    elif [ "$OS_TYPE" = "Darwin" ] && command -v sysctl >/dev/null 2>&1; then
        TOTAL_RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 0)
        TOTAL_RAM_MB=$(( TOTAL_RAM_BYTES / 1024 / 1024 ))
        AVAIL_RAM_MB=$(( TOTAL_RAM_MB / 2 ))
    fi
    TOTAL_RAM_MB="${TOTAL_RAM_MB:-0}"
    AVAIL_RAM_MB="${AVAIL_RAM_MB:-0}"
    TOTAL_RAM_GB=$(awk "BEGIN {printf \"%.1f\", ${TOTAL_RAM_MB} / 1024}")

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
            GPU_NAME="$(lspci 2>/dev/null | grep -iE 'vga|3d|display' | head -n1 | cut -d: -f3- | sed -e 's/^[[:space:]]*//')"
        fi
    fi

    # Sanitize strings for valid JSON
    DISTRO_NAME="$(echo "$DISTRO_NAME" | tr -d '\"' | tr -d '\r\n')"
    GPU_NAME="$(echo "$GPU_NAME" | tr -d '\"' | tr -d '\r\n')"

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
    load_target_port

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
    "default_port": $TARGET_PORT,
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
    load_target_port
    resolve_docker_and_compose

    case "$MODE" in
        stop)
            print_banner
            log_stage "Stopping Zenith services..."
            $COMPOSE_CMD down 2>/dev/null || true
            local native_pid_file="$ZENITH_DIR/data/zenith-native.pid"
            if [ -f "$native_pid_file" ]; then
                local n_pid
                n_pid="$(cat "$native_pid_file" 2>/dev/null || true)"
                if [ -n "$n_pid" ] && kill -0 "$n_pid" 2>/dev/null; then
                    kill "$n_pid" 2>/dev/null || true
                    log_ok "Native engine process stopped."
                fi
                rm -f "$native_pid_file"
            fi
            if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
                "$ZENITH_DIR/scripts/setup-worker.sh" stop 2>/dev/null || true
            fi
            log_ok "Zenith services stopped."
            exit 0
            ;;
        restart)
            print_banner
            log_stage "Restarting Zenith services..."
            local native_pid_file="$ZENITH_DIR/data/zenith-native.pid"
            if [ -f "$native_pid_file" ]; then
                local n_pid
                n_pid="$(cat "$native_pid_file" 2>/dev/null || true)"
                if [ -n "$n_pid" ] && kill -0 "$n_pid" 2>/dev/null; then
                    kill "$n_pid" 2>/dev/null || true
                fi
                rm -f "$native_pid_file"
                start_native_engine "Restarting native engine..."
            else
                $COMPOSE_CMD restart
            fi
            if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
                "$ZENITH_DIR/scripts/setup-worker.sh" restart 2>/dev/null || true
            fi
            log_ok "Zenith restarted."
            exit 0
            ;;
        logs)
            $COMPOSE_CMD logs -f
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
            $COMPOSE_CMD ps
            local native_pid_file="$ZENITH_DIR/data/zenith-native.pid"
            if [ -f "$native_pid_file" ]; then
                local n_pid
                n_pid="$(cat "$native_pid_file" 2>/dev/null || true)"
                if [ -n "$n_pid" ] && kill -0 "$n_pid" 2>/dev/null; then
                    echo -e "${GREEN}Zenith Native Host Process active (PID: $n_pid)${RESET}"
                fi
            fi
            echo ""
            echo -e "${DIM}Healthcheck (/api/health on port $TARGET_PORT):${RESET}"
            if curl -fsSL "http://localhost:${TARGET_PORT}/api/health" 2>/dev/null; then
                echo ""
                log_ok "Zenith is online and responding."
            else
                log_warn "Zenith is not responding on http://localhost:${TARGET_PORT}"
            fi

            echo -e "\n${DIM}Antigravity Worker (port 8022):${RESET}"
            if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
                "$ZENITH_DIR/scripts/setup-worker.sh" status 2>/dev/null || true
            fi
            exit 0
            ;;
        uninstall)
            print_banner
            log_stage "Zenith Safe Uninstaller"
            echo -e "${YELLOW}This will stop and remove Zenith containers.${RESET}"
            if prompt_confirm "Stop Zenith containers and network?" "y"; then
                $COMPOSE_CMD down
                log_ok "Containers stopped."
            fi

            if prompt_confirm "Do you also want to remove persistent volumes (user memory, data, documents)?" "n"; then
                $COMPOSE_CMD down -v
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

CURRENT_UID="$(id -u 2>/dev/null || echo 1000)"
SUDO_CMD=""
if [ "$CURRENT_UID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO_CMD="sudo"
    fi
fi

INSTALL_DOCKER=0
if ! command -v docker >/dev/null 2>&1; then
    INSTALL_DOCKER=1
fi

if [ "$INSTALL_DOCKER" -eq 1 ]; then
    log_warn "Docker is not installed on this host."
    echo -e "  Zenith requires Docker Engine to provide isolated, reproducible, non-root execution."

    if prompt_confirm "Install official Docker packages for $DISTRO_NAME now?" "y"; then
        if [ "$CURRENT_UID" -ne 0 ] && [ -z "$SUDO_CMD" ]; then
            start_native_engine "Elevated privileges (sudo) not found for Docker installation. Falling back to Zenith Native Host Mode."
        fi

        log_info "Initiating official Docker installation for $DISTRO_ID..."

        case "$DISTRO_ID" in
            ubuntu|debian|pop|mint|raspbian|kali|zorin)
                log_info "Running official Docker convenience installer (get.docker.com)..."
                curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
                $SUDO_CMD sh /tmp/get-docker.sh || true
                rm -f /tmp/get-docker.sh
                ;;
            fedora|rhel|centos|rocky|alma)
                log_info "Installing Docker via package manager..."
                $SUDO_CMD dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || \
                $SUDO_CMD dnf install -y docker docker-compose 2>/dev/null || true
                ;;
            arch|manjaro)
                log_info "Installing Docker via pacman..."
                $SUDO_CMD pacman -Sy --noconfirm docker docker-compose 2>/dev/null || true
                ;;
            alpine)
                log_info "Installing Docker via apk..."
                $SUDO_CMD apk add docker docker-cli-compose 2>/dev/null || true
                ;;
            macos)
                log_warn "On macOS, Docker Desktop is recommended."
                if command -v brew >/dev/null 2>&1; then
                    log_info "Installing Docker Desktop via Homebrew..."
                    brew install --cask docker 2>/dev/null || true
                    open -a Docker || true
                fi
                ;;
            *)
                log_info "Attempting official Docker script for $DISTRO_ID..."
                curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
                $SUDO_CMD sh /tmp/get-docker.sh || true
                rm -f /tmp/get-docker.sh
                ;;
        esac

        # Start and enable Docker service on Linux
        if [ "$OS_TYPE" = "Linux" ] && command -v systemctl >/dev/null 2>&1; then
            log_info "Enabling and starting Docker service..."
            $SUDO_CMD systemctl enable --now docker 2>/dev/null || true
        elif [ "$OS_TYPE" = "Linux" ] && command -v service >/dev/null 2>&1; then
            $SUDO_CMD service docker start 2>/dev/null || true
        fi

        # Add current user to docker group
        if [ "$CURRENT_UID" -ne 0 ] && [ "$OS_TYPE" = "Linux" ]; then
            if getent group docker >/dev/null 2>&1; then
                log_info "Granting $CURRENT_USER permission to execute Docker commands..."
                $SUDO_CMD usermod -aG docker "$CURRENT_USER" 2>/dev/null || true
            fi
        fi
    else
        start_native_engine "Docker installation declined. Falling back to Zenith Native Host Mode."
    fi
fi

# Verify Docker daemon is actively responding
DOCKER_CMD="docker"
DOCKER_READY=false
if docker info >/dev/null 2>&1; then
    DOCKER_READY=true
elif [ -n "$SUDO_CMD" ] && $SUDO_CMD docker info >/dev/null 2>&1; then
    DOCKER_READY=true
    DOCKER_CMD="$SUDO_CMD docker"
    log_info "Using elevated docker command for current session."
fi

if [ "$DOCKER_READY" != true ]; then
    start_docker_engine || true
    if docker info >/dev/null 2>&1; then
        DOCKER_READY=true
        DOCKER_CMD="docker"
    elif [ -n "$SUDO_CMD" ] && $SUDO_CMD docker info >/dev/null 2>&1; then
        DOCKER_READY=true
        DOCKER_CMD="$SUDO_CMD docker"
    fi
fi

if [ "$DOCKER_READY" != true ]; then
    start_native_engine "Docker daemon could not be ignited automatically. Falling back to Zenith Native Host Mode."
fi

DOCKER_VERSION="$($DOCKER_CMD --version | cut -d, -f1)"
log_ok "$DOCKER_VERSION active and responsive"

# ── STAGE 3: INSTALLING MISSING DEPENDENCIES ──────────────────────────────────
log_stage "[3/8] Installing missing dependencies..."

if ! command -v git >/dev/null 2>&1; then
    ensure_git_installed || true
fi
if ! command -v python3 >/dev/null 2>&1; then
    ensure_python_installed || true
fi

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
    OS_NAME_LOWER="$(echo "$OS_TYPE" | tr '[:upper:]' '[:lower:]')"
    COMPOSE_ARCH="$ARCH"
    case "$ARCH" in
        x86_64) COMPOSE_ARCH="x86_64" ;;
        aarch64|arm64) COMPOSE_ARCH="aarch64" ;;
        armv7*|armhf) COMPOSE_ARCH="armv7" ;;
        *) COMPOSE_ARCH="x86_64" ;;
    esac
    LATEST_COMPOSE_URL="https://github.com/docker/compose/releases/latest/download/docker-compose-${OS_NAME_LOWER}-${COMPOSE_ARCH}"
    if curl -fsSL "$LATEST_COMPOSE_URL" -o "$DOCKER_CONFIG/cli-plugins/docker-compose" 2>/dev/null; then
        chmod +x "$DOCKER_CONFIG/cli-plugins/docker-compose" 2>/dev/null || true
        if $DOCKER_CMD compose version >/dev/null 2>&1; then
            COMPOSE_CMD="$DOCKER_CMD compose"
            log_ok "Docker Compose plugin installed to user CLI plugins."
        else
            start_native_engine "Downloaded Docker Compose plugin could not be executed. Falling back to Zenith Native Host Mode."
        fi
    else
        start_native_engine "Failed to download Docker Compose plugin. Falling back to Zenith Native Host Mode."
    fi
fi

# ── STAGE 4: VALIDATING ZENITH CONFIGURATION ──────────────────────────────────
log_stage "[4/8] Validating Zenith configuration..."

# 1. Disk Space check (at least 2GB free)
FREE_DISK_MB=0
if command -v df >/dev/null 2>&1; then
    FREE_DISK_KB=$(df -Pk . 2>/dev/null | awk 'NR==2 {print $4}')
    FREE_DISK_KB="${FREE_DISK_KB:-0}"
    FREE_DISK_MB=$(( FREE_DISK_KB / 1024 ))
    FREE_DISK_GB=$(awk "BEGIN {printf \"%.1f\", ${FREE_DISK_MB:-0} / 1024}")
    if [ "${FREE_DISK_MB:-0}" -lt 2000 ]; then
        log_warn "Low disk space: only ${FREE_DISK_GB} GB available. 2+ GB recommended."
    else
        log_ok "Disk space: ${FREE_DISK_GB} GB available"
    fi
fi

# 2. Directory structure check
mkdir -p data data/memory static/screenshots /tmp/zenith-files 2>/dev/null || true
log_ok "Directory structure verified"

# 3. Environment (.env) merge & validation
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
            if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "${line// }" ]] || [[ ! "$line" =~ = ]]; then
                continue
            fi
            KEY="$(echo "$line" | cut -d= -f1 | tr -d ' ')"
            if [ -n "$KEY" ] && ! grep -E -q "^[[:space:]]*${KEY}[[:space:]]*=" .env; then
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

load_target_port

# 4. Port check
PORT_OCCUPIED=false

if command -v ss >/dev/null 2>&1; then
    if ss -tuln 2>/dev/null | grep -qE ":${TARGET_PORT}([[:space:]]|$)"; then
        PORT_OCCUPIED=true
    fi
elif command -v netstat >/dev/null 2>&1; then
    if netstat -tuln 2>/dev/null | grep -qE ":${TARGET_PORT}([[:space:]]|$)"; then
        PORT_OCCUPIED=true
    fi
elif command -v lsof >/dev/null 2>&1; then
    if lsof -i :"$TARGET_PORT" >/dev/null 2>&1; then
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

# Check GEMINI_API_KEY without ever printing secrets to terminal
GEMINI_CONFIGURED=false
if grep -E -q "^[[:space:]]*GEMINI_API_KEY[[:space:]]*=" .env 2>/dev/null; then
    KEY_VAL="$(grep -E "^[[:space:]]*GEMINI_API_KEY[[:space:]]*=" .env | tail -n1 | cut -d= -f2- | cut -d# -f1 | tr -d '\"'\'' ')"
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

# Initialize and start Antigravity Coding Worker on the host
if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
    log_info "Configuring Antigravity Coding Worker (agy)..."
    "$ZENITH_DIR/scripts/setup-worker.sh" install-and-start || log_warn "Antigravity worker startup encountered a warning; continuing..."
fi

IS_RUNNING=false
if [ -n "$($COMPOSE_CMD ps -q --status running zenith 2>/dev/null)" ]; then
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

printf "  "
while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    if curl -fsSL "$HEALTH_URL" 2>/dev/null | grep -qiE '"status"[[:space:]]*:[[:space:]]*"ok"|Zenith'; then
        IS_HEALTHY=true
        break
    fi
    printf "•"
    sleep 1.5
    ATTEMPT=$(( ATTEMPT + 1 ))
done
printf "\n"

if [ "$IS_HEALTHY" = true ]; then
    log_ok "Healthcheck verified: Zenith is online and responsive!"
    if [ -f "$ZENITH_DIR/scripts/setup-worker.sh" ]; then
        if [ ! -f "$HOME/.gemini/antigravity-cli/antigravity-oauth-token" ] && [ ! -f "$HOME/.gemini/credentials.json" ]; then
            echo -e "\n  ${YELLOW}💡 First-Time Antigravity Setup:${RESET}"
            echo -e "     To enable autonomous coding agents, run ${BOLD}agy${RESET} once in your terminal to sign in with Google.\n"
        fi
    fi
else
    log_err "Zenith did not report healthy within $(( MAX_ATTEMPTS * 3 / 2 ))s."
    echo -e "\n${DIM}Recent Container Diagnostic Logs:${RESET}"
    $COMPOSE_CMD logs --tail=25 || true
    echo -e "\n${YELLOW}Troubleshooting:${RESET}"
    echo "  1. Check full logs:    ${BOLD}$COMPOSE_CMD logs -f${RESET}"
    echo "  2. Try repair build:   ${BOLD}./zenith-install.sh --repair${RESET}"
    echo "  3. Verify port $TARGET_PORT:   ${BOLD}curl -v http://localhost:$TARGET_PORT/api/health${RESET}"
    exit 1
fi

# ── STAGE 8: OPENING ZENITH ───────────────────────────────────────────────────
log_stage "[8/8] Opening Zenith..."

if [ -f "$ZENITH_DIR/scripts/create-desktop-shortcut.sh" ]; then
    bash "$ZENITH_DIR/scripts/create-desktop-shortcut.sh" >/dev/null 2>&1 || true
fi

BROWSER_LAUNCHED=false

if [ "$IS_WSL" = true ]; then
    if command -v wslview >/dev/null 2>&1; then
        if wslview "$TARGET_URL" >/dev/null 2>&1; then
            BROWSER_LAUNCHED=true
        fi
    elif command -v cmd.exe >/dev/null 2>&1; then
        if cmd.exe /c start "$TARGET_URL" >/dev/null 2>&1; then
            BROWSER_LAUNCHED=true
        fi
    elif command -v powershell.exe >/dev/null 2>&1; then
        if powershell.exe -NoProfile -Command "Start-Process '$TARGET_URL'" >/dev/null 2>&1; then
            BROWSER_LAUNCHED=true
        fi
    fi
elif [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ] || [ "$OS_TYPE" = "Darwin" ]; then
    if [ "$OS_TYPE" = "Darwin" ] && command -v open >/dev/null 2>&1; then
        if open "$TARGET_URL" >/dev/null 2>&1; then
            BROWSER_LAUNCHED=true
        fi
    elif command -v xdg-open >/dev/null 2>&1; then
        if xdg-open "$TARGET_URL" >/dev/null 2>&1; then
            BROWSER_LAUNCHED=true
        fi
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
