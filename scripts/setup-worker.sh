#!/usr/bin/env bash
#
# Zenith Antigravity Worker Bootstrapper & Lifecycle Orchestrator
# Compatible with Linux, macOS, and WSL2 environments.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

mkdir -p "$ROOT_DIR/data"
WORKER_DIR="$ROOT_DIR/worker"
WORKER_VENV="$WORKER_DIR/.venv"
ROOT_VENV="$ROOT_DIR/.venv"

ACTION="${1:-install-and-start}"

# Terminal color helpers
if [ -t 1 ]; then
    GREEN="\033[0;32m"
    YELLOW="\033[1;33m"
    BLUE="\033[0;34m"
    RED="\033[0;31m"
    RESET="\033[0m"
else
    GREEN=""
    YELLOW=""
    BLUE=""
    RED=""
    RESET=""
fi

log_ok()   { printf "  ${GREEN}✓${RESET} %s\n" "$*"; }
log_info() { printf "  ${BLUE}ℹ${RESET} %s\n" "$*"; }
log_warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$*"; }
log_err()  { printf "  ${RED}✗${RESET} %s\n" "$*"; }

ensure_path() {
    local user_bin="$HOME/.local/bin"
    if [ -d "$user_bin" ] && [[ ":$PATH:" != *":$user_bin:"* ]]; then
        export PATH="$user_bin:$PATH"
    fi
}

install_agy() {
    ensure_path
    if command -v agy >/dev/null 2>&1 || command -v antigravity >/dev/null 2>&1; then
        local agy_path
        agy_path="$(command -v agy 2>/dev/null || command -v antigravity 2>/dev/null)"
        log_ok "Antigravity CLI (agy) found at: $agy_path"
        return 0
    fi

    if [ -x "$HOME/.local/bin/agy" ]; then
        log_ok "Antigravity CLI (agy) found at: $HOME/.local/bin/agy"
        export PATH="$HOME/.local/bin:$PATH"
        return 0
    fi

    log_info "Antigravity CLI (agy) not found. Installing via official Google installer..."
    if curl -fsSL https://antigravity.google/cli/install.sh | bash; then
        ensure_path
        if command -v agy >/dev/null 2>&1 || [ -x "$HOME/.local/bin/agy" ]; then
            log_ok "Antigravity CLI installed successfully."
        else
            log_warn "Installer completed, but 'agy' is not yet in current shell PATH. Added ~/.local/bin."
        fi
    else
        log_err "Failed to download or run Antigravity CLI installer."
        log_info "Manual install command: curl -fsSL https://antigravity.google/cli/install.sh | bash"
        return 1
    fi
}

setup_venv() {
    local target_venv="$WORKER_VENV"
    if [ ! -d "$target_venv" ] && [ -d "$ROOT_VENV" ]; then
        # If root .venv has fastapi and uvicorn, we can use it, or create a dedicated one
        if "$ROOT_VENV/bin/python" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
            target_venv="$ROOT_VENV"
        fi
    fi

    if [ ! -d "$target_venv" ]; then
        log_info "Creating dedicated virtualenv in worker/.venv..."
        if command -v python3 >/dev/null 2>&1; then
            python3 -m venv "$WORKER_VENV" || {
                log_warn "python3 -m venv failed. Trying --without-pip or fallback..."
                python3 -m venv --without-pip "$WORKER_VENV" || true
            }
            target_venv="$WORKER_VENV"
        else
            log_err "Python 3 is required to run the Antigravity worker."
            return 1
        fi
    fi

    local pip_bin="$target_venv/bin/pip"
    if [ -x "$pip_bin" ] && [ -f "$WORKER_DIR/requirements.txt" ]; then
        log_info "Installing worker requirements (fastapi, uvicorn)..."
        "$pip_bin" install -q -r "$WORKER_DIR/requirements.txt" || {
            log_warn "pip install returned non-zero; attempting pip install fastapi uvicorn httpx..."
            "$pip_bin" install -q fastapi uvicorn httpx || true
        }
        log_ok "Worker environment ready ($target_venv)"
    fi
}

resolve_py() {
    if [ -x "$WORKER_VENV/bin/python" ]; then
        echo "$WORKER_VENV/bin/python"
    elif [ -x "$ROOT_VENV/bin/python" ]; then
        echo "$ROOT_VENV/bin/python"
    else
        command -v python3 || echo "python"
    fi
}

case "$ACTION" in
    install)
        log_info "Setting up Antigravity Coding Worker dependencies..."
        install_agy
        setup_venv
        ;;
    start)
        ensure_path
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage start
        ;;
    stop)
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage stop
        ;;
    restart)
        ensure_path
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage restart
        ;;
    status)
        ensure_path
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage status
        ;;
    login)
        ensure_path
        install_agy
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage login
        ;;
    install-and-start|"")
        ensure_path
        install_agy
        setup_venv
        PY="$(resolve_py)"
        cd "$ROOT_DIR"
        "$PY" -m worker.manage start
        ;;
    *)
        echo "Usage: $0 {install|start|stop|restart|status|login|install-and-start}"
        exit 1
        ;;
esac
