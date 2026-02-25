"""Claude Usage Display — main entry point.

Shows Claude Code session usage metrics on the Seeed Round Display
(GC9A01 240x240) connected to a Seeed XIAO ESP32C3.

Requires:
  - gc9a01_mpy firmware (russhughes) flashed to the device
  - Relay server running on dev machine (server/server.py)
  - config.py with WiFi and server settings
  - Font files in /fonts/ on the device
"""

import time
import gc
from machine import Pin, I2C

# Hardware drivers
import lib.display as display
import lib.wifi as wifi
from lib.touch import Touch
from lib.rtc_pcf8563 import PCF8563
import lib.api as api
import lib.ui as ui
import lib.battery as battery

# Load config
try:
    import config
except ImportError:
    config = None

# Load fonts
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


def show_status(tft, line1, line2="", show_batt=False):
    """Show a status message centered on screen."""
    display.clear(tft)
    if _font_sm:
        display.center_text(tft, _font_sm, line1, 100, 0xFFFF)
        if line2:
            display.center_text(tft, _font_sm, line2, 120, 0x7BEF)
        if show_batt:
            v = battery.voltage()
            pct = battery.percent()
            info = "{:.2f}V  {}%".format(v, pct)
            display.center_text(tft, _font_sm, info, 150, 0x7BEF)


def main():
    # Init display
    tft = display.init()
    display.clear(tft)

    # Check fonts
    if _font_lg is None or _font_sm is None:
        show_status(tft, "Missing fonts!", "Upload to /fonts/")
        return

    # Set fonts in UI module
    ui.font_lg = _font_lg
    ui.font_sm = _font_sm

    # Check config
    if config is None:
        show_status(tft, "No config.py!", "Copy config_example")
        return

    show_status(tft, "Starting...")

    # Init I2C (shared bus for touch + RTC)
    i2c = I2C(0, sda=Pin(6), scl=Pin(7), freq=400_000)

    # Init peripherals
    touch = Touch(i2c, int_pin=20)
    rtc = PCF8563(i2c)

    # Wait for power to stabilize on battery boot
    time.sleep(2)

    # Connect WiFi (retry forever — critical for battery-only boot)
    wlan = None
    for attempt in range(1, 100):
        show_status(tft, "WiFi... #{}".format(attempt), config.WIFI_SSID, show_batt=True)
        try:
            wlan = wifi.connect(config.WIFI_SSID, config.WIFI_PASS)
            break
        except RuntimeError:
            time.sleep(3)
    if wlan is None or not wlan.isconnected():
        show_status(tft, "WiFi failed!", "Rebooting...", show_batt=True)
        time.sleep(5)
        import machine
        machine.reset()
    ip = wifi.ip(wlan)
    show_status(tft, "Connected", ip or "")
    time.sleep(1)

    # Sync RTC from NTP
    try:
        import ntptime
        ntptime.settime()
        t = time.localtime()
        rtc.datetime((t[0] % 100, t[1], t[2], t[6], t[3], t[4], t[5]))
    except Exception:
        pass

    # Initial data fetch
    show_status(tft, "Fetching data...")
    data = api.fetch(config.SERVER_URL)
    gc.collect()

    # State
    screen = 0
    last_fetch = time.time()
    last_touch = 0
    refresh = getattr(config, "REFRESH_INTERVAL", 10)

    # Initial render
    ui.draw_screen(tft, screen, data)

    # Main loop — wrapped in try/except so USB disconnect doesn't kill it
    while True:
        try:
            now = time.time()

            # Handle touch (with 400ms debounce)
            if now - last_touch > 0.4:
                point = touch.read()
                if point:
                    last_touch = now
                    if point[0] < 120:
                        screen = (screen - 1) % ui.NUM_SCREENS
                    else:
                        screen = (screen + 1) % ui.NUM_SCREENS
                    ui.draw_screen(tft, screen, data)

            # Periodic data refresh
            if now - last_fetch >= refresh:
                try:
                    wifi.ensure_connected(wlan, config.WIFI_SSID, config.WIFI_PASS)
                    new_data = api.fetch(config.SERVER_URL)
                    if new_data is not None:
                        data = new_data
                except Exception:
                    pass
                last_fetch = now
                gc.collect()
                ui.draw_screen(tft, screen, data)

            time.sleep(0.05)

        except KeyboardInterrupt:
            break
        except Exception:
            # Survive any transient errors (USB disconnect, I2C glitch, etc.)
            time.sleep(1)


main()
