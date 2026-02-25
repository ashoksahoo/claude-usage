#!/usr/bin/env python3
"""Render all 4 UI screens as 240x240 PNG screenshots for README.

Mimics the exact layout from lib/ui.py using Pillow.
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

# ── RGB565 → RGB ──────────────────────────────────────────────────────────────

def c(v):
    r = ((v >> 11) & 0x1F) * 255 // 31
    g = ((v >> 5)  & 0x3F) * 255 // 63
    b = (v & 0x1F)          * 255 // 31
    return (r, g, b)

BG       = c(0x0000)
TEXT     = c(0xFFFF)
TEXT_DIM = c(0x7BEF)
ACCENT   = c(0xFD20)
BAR_FILL = c(0x4ADF)
BAR_BG   = c(0x2945)
GOOD     = c(0x07E0)
WARN     = c(0xFFE0)
BAD      = c(0xF800)
SEP      = c(0x3186)
DOTS_OFF = c(0x4208)
DARK     = c(0x2104)

# ── Fonts ─────────────────────────────────────────────────────────────────────
# Simulate vga1_8x16 (8px wide, 16px tall) and vga1_bold_16x32 (16px wide, 32px tall)

_MONO_SM = "/System/Library/Fonts/Menlo.ttc"
_MONO_LG = "/System/Library/Fonts/Supplemental/Courier New Bold.ttf"

font_sm = ImageFont.truetype(_MONO_SM, 14)
font_lg = ImageFont.truetype(_MONO_LG, 28)

# Fixed char dimensions matching MicroPython bitmap fonts
SM_W, SM_H = 8, 16
LG_W, LG_H = 16, 32

# ── Drawing helpers ───────────────────────────────────────────────────────────

def fill_rect(draw, x, y, w, h, color):
    draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)

def text_sm(draw, s, x, y, color):
    draw.text((x, y), s, font=font_sm, fill=color)

def text_lg(draw, s, x, y, color):
    draw.text((x, y), s, font=font_lg, fill=color)

def center_text_sm(draw, s, y, color):
    w = len(s) * SM_W
    x = (240 - w) // 2
    text_sm(draw, s, x, y, color)

def center_text_lg(draw, s, y, color):
    w = len(s) * LG_W
    x = (240 - w) // 2
    text_lg(draw, s, x, y, color)

def draw_hbar(draw, x, y, max_w, frac, h, color):
    w = int(max_w * min(frac, 1.0))
    if w > 0:
        fill_rect(draw, x, y, w, h, color)

def draw_progress_bar(draw, x, y, w, h, pct):
    fill_rect(draw, x, y, w, h, BAR_BG)
    fill_w = int(w * min(pct / 100, 1.0))
    if fill_w > 0:
        color = BAR_FILL if pct < 50 else (WARN if pct < 80 else BAD)
        fill_rect(draw, x, y, fill_w, h, color)

def draw_widget(draw, y, label, value_str, pct, subtitle):
    lx = 35
    text_sm(draw, label, lx, y, TEXT)
    vw = len(value_str) * SM_W
    text_sm(draw, value_str, 205 - vw, y, TEXT)
    draw_progress_bar(draw, lx, y + 17, 170, 7, pct)
    text_sm(draw, subtitle, lx, y + 28, TEXT_DIM)

def draw_dots(draw, current, total):
    dot_w, gap = 6, 5
    total_w = total * dot_w + (total - 1) * gap
    x = (240 - total_w) // 2
    y = 222
    for i in range(total):
        color = ACCENT if i == current else DOTS_OFF
        fill_rect(draw, x + i * (dot_w + gap), y, dot_w, 3, color)

def fmt_tokens(n):
    if n >= 1_000_000:
        return "{:.2f}M".format(n / 1_000_000)
    if n >= 1_000:
        return "{:.1f}K".format(n / 1_000)
    return str(n)

def fmt_cost(c):
    return "${:.2f}".format(c)

def new_frame():
    img = Image.new("RGB", (240, 240), BG)
    draw = ImageDraw.Draw(img)
    return img, draw

def apply_circle_mask(img):
    mask = Image.new("L", (240, 240), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse([0, 0, 239, 239], fill=255)
    result = Image.new("RGB", (240, 240), (20, 20, 20))
    result.paste(img, mask=mask)
    return result

def save(img, name):
    out = os.path.join(os.path.dirname(__file__), "..", "docs", name)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out)
    print(f"Saved: {out}")

# ── Sample data ───────────────────────────────────────────────────────────────

DATA = {
    "plan": "max5",
    "utilization": {
        "session": {"pct": 35, "reset_label": "3h 22m"},
        "weekly":  {"pct": 68, "reset_label": "Fri 00:00"},
        "sonnet":  {"pct": 82, "reset_label": "Fri 00:00"},
    },
    "clock": {
        "hour": 14, "minute": 32,
        "day": 26, "month": 2, "year": 2026, "weekday": 3,
    },
    "daily": {"cost_usd": 8.47},
    "session": {
        "input_tokens":       85_000,
        "output_tokens":      32_000,
        "cache_write_tokens": 12_000,
        "cache_read_tokens":  45_000,
    },
    "models": {
        "claude-opus-4-6-20251101":    {"cost": 6.23, "input": 45_000, "output": 18_000},
        "claude-sonnet-4-6-20251101":  {"cost": 1.84, "input": 32_000, "output": 11_000},
        "claude-haiku-4-5-20251001":   {"cost": 0.40, "input":  8_000, "output":  3_000},
    },
}

# ── Screen 0: Dashboard ───────────────────────────────────────────────────────

def render_dashboard(data):
    img, draw = new_frame()
    u = data.get("utilization", {})

    plan = data.get("plan", "").upper()
    center_text_sm(draw, plan, 24, ACCENT)

    sess = u.get("session", {})
    draw_widget(draw, 46, "Session", "{}%".format(sess.get("pct", 0)),
                sess.get("pct", 0), "Resets {}".format(sess.get("reset_label", "")))

    fill_rect(draw, 50, 92, 140, 1, SEP)

    week = u.get("weekly", {})
    draw_widget(draw, 100, "Weekly", "{}%".format(week.get("pct", 0)),
                week.get("pct", 0), "Resets {}".format(week.get("reset_label", "")))

    fill_rect(draw, 50, 146, 140, 1, SEP)

    son = u.get("sonnet", {})
    draw_widget(draw, 154, "Sonnet", "{}%".format(son.get("pct", 0)),
                son.get("pct", 0), "Resets {}".format(son.get("reset_label", "")))

    draw_dots(draw, 0, 4)
    return apply_circle_mask(img)

# ── Screen 1: Clock ───────────────────────────────────────────────────────────

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS   = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

def render_clock(data):
    img, draw = new_frame()
    c = data.get("clock", {})

    time_str = "{:02d}:{:02d}".format(c.get("hour", 0), c.get("minute", 0))
    center_text_lg(draw, time_str, 88, TEXT)

    date_str = "{} {} {}, {}".format(
        WEEKDAYS[c.get("weekday", 0)],
        MONTHS[c.get("month", 1)],
        c.get("day", 1),
        c.get("year", 2026),
    )
    center_text_sm(draw, date_str, 130, TEXT_DIM)

    d = data.get("daily", {})
    if d.get("cost_usd", 0) > 0:
        center_text_sm(draw, "Today: " + fmt_cost(d["cost_usd"]), 158, ACCENT)

    pct, volts = 85, 4.12
    batt_color = GOOD if pct > 60 else (WARN if pct > 20 else BAD)
    center_text_sm(draw, "{}%  {:.2f}V".format(pct, volts), 190, batt_color)

    draw_dots(draw, 1, 4)
    return apply_circle_mask(img)

# ── Screen 2: Tokens ──────────────────────────────────────────────────────────

def render_tokens(data):
    img, draw = new_frame()
    s = data.get("session", {})

    center_text_sm(draw, "TOKENS", 38, ACCENT)

    items = [
        ("Input",   s.get("input_tokens", 0)),
        ("Output",  s.get("output_tokens", 0)),
        ("Cache W", s.get("cache_write_tokens", 0)),
        ("Cache R", s.get("cache_read_tokens", 0)),
    ]

    max_val = max((v for _, v in items), default=1) or 1
    y = 62
    for label, val in items:
        text_sm(draw, label, 30, y, TEXT_DIM)
        bar_color = ACCENT if val > 0 else DARK
        draw_hbar(draw, 30, y + 16, 120, val / max_val, 6, bar_color)
        text_sm(draw, fmt_tokens(val), 160, y, TEXT)
        y += 32

    d = data.get("daily", {})
    y += 4
    fill_rect(draw, 40, y, 160, 1, DOTS_OFF)
    y += 8
    center_text_sm(draw, "Today: " + fmt_cost(d.get("cost_usd", 0)), y, ACCENT)

    draw_dots(draw, 2, 4)
    return apply_circle_mask(img)

# ── Screen 3: Models ──────────────────────────────────────────────────────────

def shorten_model(name):
    parts = name.replace("claude-", "").split("-")
    if len(parts) >= 2:
        result = parts[0]
        for p in parts[1:]:
            if len(p) <= 3:
                result += "-" + p
        return result
    return name[:15]

def render_models(data):
    img, draw = new_frame()
    models = data.get("models", {})

    center_text_sm(draw, "MODELS", 38, ACCENT)

    y = 62
    sorted_models = sorted(models.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    for name, stats in sorted_models[:5]:
        short = shorten_model(name)
        text_sm(draw, short, 24, y, TEXT)
        text_sm(draw, fmt_cost(stats["cost"]), 150, y, ACCENT)
        y += 16
        tok_str = "  i:{} o:{}".format(
            fmt_tokens(stats.get("input", 0)),
            fmt_tokens(stats.get("output", 0)),
        )
        text_sm(draw, tok_str, 24, y, TEXT_DIM)
        y += 22

    total_cost = sum(m["cost"] for m in models.values())
    y = max(y + 4, 185)
    fill_rect(draw, 40, y, 160, 1, DOTS_OFF)
    y += 8
    center_text_sm(draw, "Total " + fmt_cost(total_cost), y, TEXT)

    draw_dots(draw, 3, 4)
    return apply_circle_mask(img)

# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    save(render_dashboard(DATA), "screen0_dashboard.png")
    save(render_clock(DATA),     "screen1_clock.png")
    save(render_tokens(DATA),    "screen2_tokens.png")
    save(render_models(DATA),    "screen3_models.png")
    print("Done.")
