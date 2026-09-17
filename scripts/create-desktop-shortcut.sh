#!/usr/bin/env bash
#
# Creates a Linux desktop shortcut for Zenith
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ICON_PATH="$ROOT_DIR/static/favicon.svg"
EXEC_PATH="$ROOT_DIR/start.sh"

DESKTOP_ENTRY="[Desktop Entry]
Version=1.0
Type=Application
Name=Zenith
Comment=Autonomous AI Operating Layer
Exec=$EXEC_PATH
Icon=$ICON_PATH
Terminal=true
Categories=Utility;Development;
StartupNotify=true
"

mkdir -p "$HOME/.local/share/applications"
echo "$DESKTOP_ENTRY" > "$HOME/.local/share/applications/zenith.desktop"
chmod +x "$HOME/.local/share/applications/zenith.desktop"

if [ -d "$HOME/Desktop" ]; then
    echo "$DESKTOP_ENTRY" > "$HOME/Desktop/Zenith.desktop"
    chmod +x "$HOME/Desktop/Zenith.desktop" 2>/dev/null || true
fi

echo "Desktop shortcut created for Zenith."
