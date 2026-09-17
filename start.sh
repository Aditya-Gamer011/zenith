#!/usr/bin/env bash
# Zenith Quick Launcher
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/zenith-install.sh" "$@"
