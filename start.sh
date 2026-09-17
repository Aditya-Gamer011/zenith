#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# Zenith Quick Launcher & Standalone Initializer
# ══════════════════════════════════════════════════════════════════════════════
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd || true)"

if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/zenith-install.sh" ]; then
    exec "$SCRIPT_DIR/zenith-install.sh" "$@"
elif [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/scripts/zenith-install.sh" ]; then
    exec "$SCRIPT_DIR/scripts/zenith-install.sh" "$@"
elif [ -f "$HOME/.zenith/app/zenith-install.sh" ]; then
    exec "$HOME/.zenith/app/zenith-install.sh" "$@"
else
    echo "[Zenith] Standalone launcher: Zenith installer not found locally."
    mkdir -p "$HOME/.zenith/app"
    TARGET="$HOME/.zenith/app/zenith-install.sh"
    echo "[Zenith] Downloading Zenith installer from GitHub..."
    if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
        echo "[Zenith] Neither curl nor wget found. Attempting automatic installation..."
        SUDO=""
        if [ "$(id -u 2>/dev/null || echo 1000)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
            SUDO="sudo"
        fi
        if command -v apt-get >/dev/null 2>&1; then
            $SUDO apt-get update -qq >/dev/null 2>&1 || true
            $SUDO apt-get install -y -qq curl >/dev/null 2>&1 || true
        elif command -v dnf >/dev/null 2>&1; then
            $SUDO dnf install -y -q curl >/dev/null 2>&1 || true
        elif command -v yum >/dev/null 2>&1; then
            $SUDO yum install -y -q curl >/dev/null 2>&1 || true
        elif command -v pacman >/dev/null 2>&1; then
            $SUDO pacman -Sy --noconfirm curl >/dev/null 2>&1 || true
        elif command -v apk >/dev/null 2>&1; then
            $SUDO apk add --no-cache curl >/dev/null 2>&1 || true
        fi
    fi

    if command -v curl >/dev/null 2>&1; then
        curl -fsSL https://raw.githubusercontent.com/Aditya-Gamer011/zenith/main/zenith-install.sh -o "$TARGET"
    elif command -v wget >/dev/null 2>&1; then
        wget -q https://raw.githubusercontent.com/Aditya-Gamer011/zenith/main/zenith-install.sh -O "$TARGET"
    else
        echo "[Zenith Error] Neither curl nor wget could be installed automatically. Please install curl or git." >&2
        exit 1
    fi
    chmod +x "$TARGET" 2>/dev/null || true
    exec "$TARGET" "$@"
fi
