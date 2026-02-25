#!/usr/bin/env bash
# Flash gc9a01_mpy firmware to XIAO ESP32C3.
#
# Prerequisites:
#   pip install esptool
#   Download firmware from:
#   https://github.com/russhughes/gc9a01_mpy/blob/main/firmware/ESP32_GENERIC_C3/firmware_4MiB.bin
#
# To enter bootloader mode on XIAO ESP32C3:
#   1. Hold the BOOT button (D9/GPIO9)
#   2. Press and release RESET
#   3. Release BOOT
#
# Usage:
#   ./tools/flash.sh firmware_4MiB.bin [port]

set -euo pipefail

FIRMWARE="${1:?Usage: $0 <firmware.bin> [port]}"
PORT="${2:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)}"

if [ -z "$PORT" ]; then
    echo "Error: No port found. Specify port as second argument."
    echo "  macOS:  /dev/cu.usbmodem*"
    echo "  Linux:  /dev/ttyACM0 or /dev/ttyUSB0"
    exit 1
fi

echo "Port:     $PORT"
echo "Firmware: $FIRMWARE"
echo ""

echo "==> Erasing flash..."
esptool.py --chip esp32c3 --port "$PORT" erase_flash

echo ""
echo "==> Flashing firmware..."
esptool.py --chip esp32c3 --port "$PORT" --baud 460800 \
    write_flash -z 0x0 "$FIRMWARE"

echo ""
echo "Done. Press RESET on the board."
