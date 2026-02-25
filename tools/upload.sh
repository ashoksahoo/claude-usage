#!/usr/bin/env bash
# Upload all project files to XIAO ESP32C3 via mpremote.
#
# Prerequisites:
#   pip install mpremote
#
# Usage:
#   ./tools/upload.sh [port]
#   ./tools/upload.sh /dev/cu.usbmodem1101

set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"

PORT="${1:-auto}"

if [ "$PORT" = "auto" ]; then
    CONNECT=""
else
    CONNECT="connect $PORT"
fi

MPR="mpremote $CONNECT"

echo "==> Uploading to ESP32C3..."
echo "    Project: $PROJECT_ROOT"

# Create directories
$MPR mkdir :lib 2>/dev/null || true
$MPR mkdir :fonts 2>/dev/null || true

# Core files
echo "  boot.py"
$MPR cp boot.py :boot.py

echo "  main.py"
$MPR cp main.py :main.py

# Config (only if exists — never overwrite on device)
if [ -f config.py ]; then
    echo "  config.py"
    $MPR cp config.py :config.py
else
    echo "  SKIP config.py (not found — copy config_example.py to config.py first)"
fi

# Library modules
for f in lib/*.py; do
    name=$(basename "$f")
    echo "  lib/$name"
    $MPR cp "$f" ":lib/$name"
done

# Font files (if any in fonts/)
for f in fonts/*.py; do
    [ -f "$f" ] || continue
    name=$(basename "$f")
    echo "  fonts/$name"
    $MPR cp "$f" ":fonts/$name"
done

echo ""
echo "Done. Reset the board to start."
echo ""
echo "To monitor serial output:"
echo "  mpremote $CONNECT repl"
