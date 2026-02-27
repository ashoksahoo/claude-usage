"""GC9A01 240x240 round display initialization and drawing helpers.

Requires the gc9a01_mpy C-driver firmware from russhughes:
https://github.com/russhughes/gc9a01_mpy

Pin mapping for XIAO ESP32C3 + Round Display:
  MOSI:      GPIO10 (D10)
  SCK:       GPIO8  (D8)
  CS:        GPIO3  (D1)
  DC:        GPIO5  (D3)
  Backlight: GPIO21 (D6)
"""

import gc9a01
from machine import Pin, SPI
import math


def init():
    """Initialize the display and return the tft object."""
    spi = SPI(1, baudrate=40_000_000, sck=Pin(8), mosi=Pin(10))
    tft = gc9a01.GC9A01(
        spi, 240, 240,
        dc=Pin(5, Pin.OUT),
        cs=Pin(3, Pin.OUT),
        backlight=Pin(21, Pin.OUT),
        rotation=0,
    )
    tft.init()
    return tft


def center_text(tft, font, text, y, fg, bg=0x0000):
    """Draw text horizontally centered at the given y coordinate."""
    w = len(text) * font.WIDTH
    x = (240 - w) // 2
    tft.text(font, text, x, y, fg, bg)


def right_text(tft, font, text, y, fg, bg=0x0000, margin=20):
    """Draw text right-aligned."""
    w = len(text) * font.WIDTH
    x = 240 - w - margin
    tft.text(font, text, x, y, fg, bg)


def draw_hbar(tft, x, y, max_w, fraction, h, color):
    """Draw a horizontal bar (for bar charts)."""
    w = int(max_w * min(fraction, 1.0))
    if w > 0:
        tft.fill_rect(x, y, w, h, color)


def draw_ring(tft, cx, cy, r, start_deg, end_deg, color, thickness=3):
    """Draw an arc ring segment. Angles: 0=top, clockwise."""
    for deg in range(start_deg, end_deg, 2):
        rad = math.radians(deg - 90)  # offset so 0=top
        cos_r = math.cos(rad)
        sin_r = math.sin(rad)
        for t in range(thickness):
            px = int(cx + (r - t) * cos_r)
            py = int(cy + (r - t) * sin_r)
            if 0 <= px < 240 and 0 <= py < 240:
                tft.pixel(px, py, color)


def clear(tft):
    """Clear the display to black."""
    tft.fill(0x0000)


# ── Weather icons ─────────────────────────────────────────────────────────────

_WX_YELLOW = 0xFFE0   # sun / lightning
_WX_GRAY   = 0xC618   # cloud / fog
_WX_BLUE   = 0x4ADF   # rain
_WX_WHITE  = 0xFFFF   # snow


def fill_circle(tft, cx, cy, r, color):
    """Draw a filled circle using horizontal spans."""
    r2 = r * r
    for dy in range(-r, r + 1):
        dx = int(math.sqrt(r2 - dy * dy))
        tft.fill_rect(cx - dx, cy + dy, 2 * dx + 1, 1, color)


def _wx_cloud(tft, cx, cy):
    fill_circle(tft, cx - 5, cy + 3, 5, _WX_GRAY)
    fill_circle(tft, cx + 5, cy + 3, 5, _WX_GRAY)
    fill_circle(tft, cx,     cy - 2, 7, _WX_GRAY)


def _wx_sun(tft, cx, cy, r=6):
    fill_circle(tft, cx, cy, r, _WX_YELLOW)
    for a in (0, 45, 90, 135, 180, 225, 270, 315):
        rad = math.radians(a)
        rx = int(cx + (r + 5) * math.cos(rad))
        ry = int(cy + (r + 5) * math.sin(rad))
        tft.fill_rect(rx - 1, ry - 1, 3, 3, _WX_YELLOW)


def draw_weather_icon(tft, cx, cy, icon):
    """Draw a ~24×24 weather icon centred at (cx, cy).

    icon: 3-char WMO code — SUN FEW OVC FOG DZL RAN SHR SNW SNS STM
    """
    if icon == "SUN":
        _wx_sun(tft, cx, cy)

    elif icon == "FEW":
        # Sun upper-right, cloud lower-center (partly cloudy)
        _wx_sun(tft, cx + 5, cy - 5, r=5)
        fill_circle(tft, cx - 4, cy + 5, 5, _WX_GRAY)
        fill_circle(tft, cx + 4, cy + 5, 5, _WX_GRAY)
        fill_circle(tft, cx,     cy + 1, 6, _WX_GRAY)

    elif icon == "OVC":
        _wx_cloud(tft, cx, cy)

    elif icon == "FOG":
        _wx_cloud(tft, cx, cy - 5)
        for i in range(3):
            tft.fill_rect(cx - 9, cy + 7 + i * 4, 18, 2, _WX_GRAY)

    elif icon in ("DZL", "RAN", "SHR"):
        _wx_cloud(tft, cx, cy - 5)
        for i, dx in enumerate((-6, 0, 6)):
            tft.fill_rect(cx + dx, cy + 8 + (i & 1) * 3, 2, 5, _WX_BLUE)

    elif icon in ("SNW", "SNS"):
        _wx_cloud(tft, cx, cy - 5)
        for dx in (-6, 0, 6):
            x0, y0 = cx + dx, cy + 9
            tft.fill_rect(x0 - 3, y0,     7, 2, _WX_WHITE)
            tft.fill_rect(x0,     y0 - 3, 2, 7, _WX_WHITE)

    elif icon == "STM":
        _wx_cloud(tft, cx, cy - 7)
        for x, y in ((3, 4), (0, 9), (4, 9), (1, 14)):
            tft.fill_rect(cx + x, cy + y, 3, 4, _WX_YELLOW)
