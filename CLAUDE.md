# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MicroPython project that displays Claude Code session usage metrics on a **Seeed XIAO ESP32C3** with the **Seeed Round Display** (GC9A01, 240x240 TFT, capacitive touch).

Architecture: two-part system:
1. **Relay server** (`server/server.py`) — Python script running on the dev machine. Reads Claude Code JSONL logs from `~/.claude/projects/**/*.jsonl`, computes session/daily metrics, and serves them over HTTP on the local network (default port 8265).
2. **Device firmware** (MicroPython on ESP32C3) — Connects to WiFi, polls the relay server every 10s, renders usage data on the round display with touch navigation between 3 screens.

## Hardware

- **MCU**: XIAO ESP32C3 (RISC-V, 160MHz, 4MB flash, ~320KB SRAM, no PSRAM)
- **Display**: GC9A01 240x240 round TFT via SPI
- **Touch**: CHSC6X capacitive controller via I2C (addr 0x2E)
- **RTC**: PCF8563 via I2C (addr 0x51, shared bus with touch)
- **Firmware**: gc9a01_mpy from russhughes (C-driver baked into MicroPython firmware)

### Pin Mapping (XIAO ESP32C3 + Round Display)

| Function     | GPIO | XIAO Pin |
|-------------|------|----------|
| SPI MOSI    | 10   | D10      |
| SPI SCK     | 8    | D8       |
| TFT CS      | 3    | D1       |
| TFT DC      | 5    | D3       |
| TFT BL      | 21   | D6       |
| I2C SDA     | 6    | D4       |
| I2C SCL     | 7    | D5       |
| Touch INT   | 20   | D7       |
| SD Card CS  | 4    | D2       |

## Commands

### Relay Server (dev machine)
```bash
# Run the relay server (reads ~/.claude/projects/ JSONL logs)
python server/server.py --plan pro --port 8265

# With different plan limits
python server/server.py --plan max5
python server/server.py --plan max20
```

### Flash Firmware
```bash
# Install tools
pip install esptool mpremote

# Download gc9a01_mpy firmware for ESP32_GENERIC_C3 (4MiB):
# https://github.com/russhughes/gc9a01_mpy/blob/main/firmware/ESP32_GENERIC_C3/firmware_4MiB.bin

# Enter bootloader: hold BOOT, press RESET, release BOOT
./tools/flash.sh firmware_4MiB.bin
```

### Upload to Device
```bash
# First time: copy and edit config
cp config_example.py config.py  # then edit with your WiFi + server IP

# Download fonts to fonts/ directory:
# https://github.com/russhughes/gc9a01_mpy/tree/main/fonts/bitmap
# Required: vga1_bold_16x32.py and vga1_8x16.py

# Upload everything
./tools/upload.sh

# Or specify port
./tools/upload.sh /dev/cu.usbmodem1101

# Monitor serial output
mpremote repl
```

## File Structure

```
server/server.py    — Relay server (runs on dev machine, zero dependencies)
boot.py             — MicroPython boot (sets sys.path)
main.py             — App entry: init hardware, WiFi, main loop
config_example.py   — Config template (copy to config.py)
lib/display.py      — GC9A01 init + drawing helpers (center_text, draw_hbar, draw_ring)
lib/ui.py           — 3 UI screens: cost gauge, token breakdown, model list
lib/api.py          — HTTP fetch from relay server
lib/wifi.py         — WiFi connect/reconnect
lib/touch.py        — CHSC6X touch driver
lib/rtc_pcf8563.py  — PCF8563 RTC driver
lib/colors.py       — RGB565 color palette + cost_color()
tools/flash.sh      — esptool firmware flash helper
tools/upload.sh     — mpremote upload helper
fonts/              — Font .py files from gc9a01_mpy (not committed)
```

## ESP32-C3 Constraints

- **No PSRAM** — all data lives in ~320KB SRAM. After WiFi: ~100-130KB free.
- Always call `gc.collect()` before/after HTTP requests.
- Always call `resp.close()` on urequests responses immediately.
- Use `from micropython import const` for integer constants (stored in flash).
- Font files must be uploaded separately — they're not in firmware.
- Flash address for ESP32-C3 is `0x0` (not `0x1000` like ESP32).
- GPIO9 has pull-up (BOOT button) — don't use as general input.
- I2C bus is shared between touch (0x2E) and RTC (0x51) — create one I2C instance.

## Data Flow

```
Claude Code CLI writes → ~/.claude/projects/**/*.jsonl
         ↓
server/server.py reads JSONL, computes metrics (session=5h window, daily)
         ↓  HTTP JSON on local network
ESP32C3 polls /api/usage every 10s
         ↓
lib/ui.py renders 3 screens on GC9A01 round display
         ↓
Touch navigation: tap left half = prev screen, tap right half = next
```

## Relay Server API

`GET /api/usage` returns:
```json
{
  "session": {
    "cost_usd": 5.23, "cost_limit": 18.0,
    "tokens_used": 12450, "token_limit": 19000,
    "messages_sent": 42, "message_limit": 250,
    "input_tokens": 8000, "output_tokens": 3000,
    "cache_write_tokens": 800, "cache_read_tokens": 650,
    "burn_rate": 42.3, "cost_rate": 0.0021,
    "minutes_remaining": 155.0
  },
  "daily": { "cost_usd": 12.50, "tokens": 45000 },
  "models": { "claude-sonnet-4-...": { "input": 5000, "output": 2000, "cost": 0.045 } },
  "plan": "pro"
}
```

Session = 5-hour sliding window (matches Claude Code rate limit window). Plan limits are empirical values from claude-monitor project. Cost is computed from token counts using per-model pricing when `costUSD` field is absent from JSONL entries.

## UI Screens

- **Screen 0 (Cost Gauge)**: Segmented arc ring showing session cost as fraction of limit. Big cost number in center. Token count, message count, burn rate, time remaining below.
- **Screen 1 (Tokens)**: Horizontal bar chart of input/output/cache-write/cache-read tokens. Daily cost summary.
- **Screen 2 (Models)**: Per-model cost and token breakdown, sorted by cost descending.

Color coding: green (<50% of limit), yellow (50-80%), red (>80%).
