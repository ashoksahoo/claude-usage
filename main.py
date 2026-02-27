"""Claude Usage Display — main entry point.

Uses uasyncio so touch polling (20ms) stays responsive even while the
HTTP fetch is in progress. Two tasks run cooperatively on the single core:
  - touch_task: polls every 20ms, renders instantly on tap
  - fetch_task: async HTTP GET, yields at every network read
"""

import time
import gc
from machine import Pin, I2C
import uasyncio as asyncio

import lib.display as display
import lib.wifi as wifi
from lib.touch import Touch
from lib.rtc_pcf8563 import PCF8563
import lib.api as api
import lib.ui as ui

try:
    import config
except ImportError:
    config = None

try:
    import vga1_bold_16x32 as _font_lg
except ImportError:
    try:
        import vga1_16x32 as _font_lg
    except ImportError:
        _font_lg = None

try:
    import vga1_8x16 as _font_sm
except ImportError:
    _font_sm = None

# ── Shared state (cooperative single-core — no locking needed) ────────────────
_data   = None
_screen = 0


def show_status(tft, line1, line2=""):
    display.clear(tft)
    if _font_sm:
        display.center_text(tft, _font_sm, line1, 100, 0xFFFF)
        if line2:
            display.center_text(tft, _font_sm, line2, 120, 0x7BEF)


def _parse_url(url):
    """'http://192.168.1.100:8265' → ('192.168.1.100', 8265)"""
    url = url.replace("http://", "").replace("https://", "").split("/")[0]
    if ":" in url:
        host, port_str = url.rsplit(":", 1)
        return host, int(port_str)
    return url, 80


# ── Tasks ─────────────────────────────────────────────────────────────────────

async def touch_task(touch, tft):
    """Poll touch every 20ms. Renders immediately on tap.

    Stays fully responsive during HTTP fetch because uasyncio yields
    at every await — network reads in fetch_task don't block this task.
    """
    global _screen
    last_ms = 0
    while True:
        ms = time.ticks_ms()
        if time.ticks_diff(ms, last_ms) > 400:
            point = touch.read()
            if point:
                last_ms = ms
                if point[0] < 120:
                    _screen = (_screen - 1) % ui.NUM_SCREENS
                else:
                    _screen = (_screen + 1) % ui.NUM_SCREENS
                ui.draw_screen(tft, _screen, _data)
        await asyncio.sleep_ms(20)


async def _reconnect(wlan):
    """Non-blocking WiFi reconnect — uses await so touch stays alive."""
    if wlan.isconnected():
        return True
    try:
        wlan.active(True)
        wlan.connect(config.WIFI_SSID, config.WIFI_PASS)
        for _ in range(20):           # 10s timeout
            if wlan.isconnected():
                return True
            await asyncio.sleep_ms(500)
    except Exception:
        pass
    return False


async def fetch_task(host, port, tft, wlan, refresh_s):
    """Fetch data every refresh_s seconds without blocking touch."""
    global _data
    while True:
        await asyncio.sleep(refresh_s)
        if not await _reconnect(wlan):
            continue
        new_data = await api.fetch_async(host, port)
        if new_data is not None:
            _data = new_data
            ui.draw_screen(tft, _screen, _data)
        gc.collect()


# ── Entry point ───────────────────────────────────────────────────────────────

async def amain():
    global _data

    tft = display.init()
    display.clear(tft)

    if _font_lg is None or _font_sm is None:
        show_status(tft, "Missing fonts!", "Upload to /fonts/")
        return

    ui.font_lg = _font_lg
    ui.font_sm = _font_sm

    if config is None:
        show_status(tft, "No config.py!", "Copy config_example")
        return

    show_status(tft, "Starting...")

    i2c = I2C(0, sda=Pin(6), scl=Pin(7), freq=400_000)
    touch = Touch(i2c, int_pin=20)
    rtc = PCF8563(i2c)

    await asyncio.sleep(2)  # power stabilise on battery boot

    # WiFi — blocking connect is fine at boot, tasks haven't started yet
    wlan = None
    for attempt in range(1, 100):
        show_status(tft, "WiFi... #{}".format(attempt), config.WIFI_SSID)
        try:
            wlan = wifi.connect(config.WIFI_SSID, config.WIFI_PASS)
            break
        except RuntimeError:
            await asyncio.sleep(3)

    if wlan is None or not wlan.isconnected():
        show_status(tft, "WiFi failed!", "Rebooting...")
        await asyncio.sleep(5)
        import machine
        machine.reset()

    show_status(tft, "Connected", wifi.ip(wlan) or "")
    await asyncio.sleep(1)

    # NTP sync
    try:
        import ntptime
        ntptime.settime()
        t = time.localtime()
        rtc.datetime((t[0] % 100, t[1], t[2], t[6], t[3], t[4], t[5]))
    except Exception:
        pass

    # Parse server address once
    host, port = _parse_url(config.SERVER_URL)

    # Initial fetch
    show_status(tft, "Fetching data...")
    _data = await api.fetch_async(host, port)
    gc.collect()

    refresh = getattr(config, "REFRESH_INTERVAL", 60)

    ui.draw_screen(tft, _screen, _data)

    # Launch tasks — touch runs every 20ms, fetch runs every refresh_s
    asyncio.create_task(touch_task(touch, tft))
    asyncio.create_task(fetch_task(host, port, tft, wlan, refresh))

    # Keep the scheduler running
    while True:
        await asyncio.sleep(60)


try:
    asyncio.run(amain())
except KeyboardInterrupt:
    pass
