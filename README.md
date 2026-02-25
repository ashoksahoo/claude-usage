# Claude Usage Display

A smart display that shows your [Claude Code](https://claude.ai/code) session usage in real time — built with MicroPython on a tiny round touchscreen.

## Hardware

- [Seeed XIAO ESP32C3](https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/) — RISC-V MCU with WiFi + BLE
- [Seeed Round Display for XIAO](https://wiki.seeedstudio.com/get_start_round_display/) — 240x240 TFT, capacitive touch, RTC, LiPo charging

The display plugs directly onto the XIAO — no wiring needed.

## How It Works

```
Claude Code CLI  ──writes──>  ~/.claude/projects/**/*.jsonl
                                        │
                              server/server.py (your computer)
                              reads logs, computes metrics
                                        │
                                   HTTP (local WiFi)
                                        │
                              ESP32C3 + Round Display
                              polls every 10s, renders UI
```

A lightweight **relay server** (zero dependencies, runs on your dev machine) reads Claude Code's local JSONL log files, computes session and daily usage metrics, and serves them as JSON over HTTP. The ESP32C3 fetches this data over WiFi and renders it on the round display.

## UI Screens

Tap left/right halves of the screen to navigate. Battery percentage shown on all screens.

| Screen | Shows |
|--------|-------|
| **Cost Gauge** | Session cost with arc ring, token count, message count, burn rate, time remaining |
| **Tokens** | Bar chart of input/output/cache tokens, daily cost |
| **Models** | Per-model cost and token breakdown |

Color coding: green (<50% of limit), yellow (50-80%), red (>80%).

## Setup

### 1. Install tools

```bash
pip install esptool mpremote
```

### 2. Flash firmware

Download the [gc9a01_mpy firmware](https://github.com/russhughes/gc9a01_mpy/blob/main/firmware/ESP32_GENERIC_C3/firmware_4MiB.bin) (MicroPython with GC9A01 display driver baked in).

Put the board in bootloader mode: hold **BOOT**, press **RESET**, release **BOOT**.

```bash
./tools/flash.sh firmware_4MiB.bin
```

### 3. Download fonts

Get these from [gc9a01_mpy/fonts/bitmap](https://github.com/russhughes/gc9a01_mpy/tree/main/fonts/bitmap) and place them in `fonts/`:

- `vga1_bold_16x32.py`
- `vga1_8x16.py`

### 4. Configure

```bash
cp config_example.py config.py
```

Edit `config.py` with your WiFi credentials and your computer's local IP:

```python
WIFI_SSID = "your-wifi"
WIFI_PASS = "your-password"
SERVER_URL = "http://192.168.1.100:8265"
```

### 5. Upload to device

```bash
./tools/upload.sh
# or specify port: ./tools/upload.sh /dev/cu.usbmodem1101
```

### 6. Start the relay server

```bash
python server/server.py --plan pro
```

Plans: `pro` (default), `max5`, `max20` — sets session token/cost/message limits.

### 7. Reset the board

Press the reset button or power cycle. The display will connect to WiFi and start showing your usage.

## Battery Operation

The Round Display supports LiPo batteries via a JST 1.25 connector. The display works untethered on battery with WiFi.

**Note:** The ESP32C3 WiFi radio draws ~350mA peaks. If your battery is low (<3.3V), WiFi will fail to connect while the display still works. Charge via USB until the voltage reads 3.5V+ (shown on the boot screen).

WiFi TX power is reduced to 13dBm (from default 20dBm) to cut peak current draw — still enough for same-room range.

## Relay Server API

`GET /api/usage` — returns session metrics, daily totals, and per-model breakdown as JSON.

`GET /health` — returns `ok`.

The server reads `~/.claude/projects/**/*.jsonl`, computes a 5-hour sliding window (matching Claude Code's rate limit window), and caches results for 5 seconds. Zero external dependencies — just Python stdlib.

## Inspired By

- [claude-monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) — terminal-based Claude Code usage monitor (session limits and pricing data sourced from this project)

## License

MIT
