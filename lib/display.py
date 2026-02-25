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
