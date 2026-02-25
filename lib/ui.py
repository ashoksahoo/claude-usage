"""UI screens for the round display.

Three screens, navigated by touch (tap left=prev, tap right=next):
  0: Cost gauge — session cost with segmented ring
  1: Token & message details
  2: Per-model breakdown

Battery percentage is shown on every screen.
"""

import math
from micropython import const
import lib.display as disp
import lib.battery as battery
from lib.colors import (
    BG, TEXT, TEXT_DIM, ACCENT, ACCENT_DIM,
    GOOD, WARN, BAD, cost_color,
)

# Loaded by main.py after display init
font_lg = None  # vga1_bold_16x32 or vga1_16x32
font_sm = None  # vga1_8x16

NUM_SCREENS = 3
_CX = const(120)
_CY = const(120)


def _fmt_tokens(n):
    """Format token count: 1234 -> '1,234', 1234567 -> '1.23M'."""
    if n >= 1_000_000:
        return "{:.2f}M".format(n / 1_000_000)
    if n >= 10_000:
        return "{:.1f}K".format(n / 1_000)
    if n >= 1_000:
        return "{:.1f}K".format(n / 1_000)
    return str(n)


def _fmt_cost(c):
    """Format cost as $X.XX."""
    return "${:.2f}".format(c)


def _fmt_time(minutes):
    """Format minutes as Xh Ym."""
    h = int(minutes // 60)
    m = int(minutes % 60)
    if h > 0:
        return "{}h {:02d}m".format(h, m)
    return "{}m".format(m)


def _pct(used, limit):
    if limit <= 0:
        return 0.0
    return min(used / limit, 1.0)


def _draw_gauge(tft, fraction, color):
    """Draw a segmented arc gauge around the display edge.

    36 segments spanning 270 degrees (from 7 o'clock to 5 o'clock).
    """
    r = 116
    segments = 36
    active = int(segments * min(max(fraction, 0), 1.0))
    start_angle = 135  # degrees, 7 o'clock position

    for i in range(segments):
        angle = start_angle + (i * 270 / segments)
        rad = math.radians(angle)
        px = int(_CX + r * math.cos(rad))
        py = int(_CY + r * math.sin(rad))

        if i < active:
            c = color
        else:
            c = 0x2104  # dark gray

        tft.fill_rect(px - 2, py - 2, 5, 5, c)


def _draw_dots(tft, current, total):
    """Draw page indicator dots at the bottom."""
    dot_w = 8
    gap = 6
    total_w = total * dot_w + (total - 1) * gap
    x = (_CX * 2 - total_w) // 2
    y = 220

    for i in range(total):
        c = ACCENT if i == current else 0x4208
        tft.fill_rect(x + i * (dot_w + gap), y, dot_w, 4, c)


def _draw_battery(tft):
    """Draw battery percentage in the top-right area."""
    pct = battery.percent()
    if pct > 60:
        color = GOOD
    elif pct > 20:
        color = WARN
    else:
        color = BAD
    text = "{}%".format(pct)
    # Position in top-right safe zone of the circle
    x = 170
    y = 22
    tft.text(font_sm, text, x, y, color)


def draw_screen(tft, screen_idx, data):
    """Render the specified screen with usage data."""
    disp.clear(tft)

    if data is None:
        disp.center_text(tft, font_sm, "No Data", 108, TEXT_DIM)
        _draw_battery(tft)
        _draw_dots(tft, screen_idx, NUM_SCREENS)
        return

    if screen_idx == 0:
        _draw_cost_screen(tft, data)
    elif screen_idx == 1:
        _draw_tokens_screen(tft, data)
    elif screen_idx == 2:
        _draw_models_screen(tft, data)

    _draw_battery(tft)
    _draw_dots(tft, screen_idx, NUM_SCREENS)


def _draw_cost_screen(tft, data):
    """Screen 0: Session cost gauge."""
    s = data.get("session", {})
    cost = s.get("cost_usd", 0)
    limit = s.get("cost_limit", 1)
    tokens = s.get("tokens_used", 0)
    msgs = s.get("messages_sent", 0)
    msg_limit = s.get("message_limit", 1)
    burn = s.get("burn_rate", 0)
    remaining = s.get("minutes_remaining", 0)

    frac = _pct(cost, limit)
    color = cost_color(cost, limit)

    # Gauge ring
    _draw_gauge(tft, frac, color)

    # Label
    disp.center_text(tft, font_sm, "SESSION", 38, ACCENT)

    # Big cost
    cost_str = _fmt_cost(cost)
    disp.center_text(tft, font_lg, cost_str, 68, color)

    # Limit
    limit_str = "/ " + _fmt_cost(limit)
    disp.center_text(tft, font_sm, limit_str, 102, TEXT_DIM)

    # Stats
    y = 128
    disp.center_text(tft, font_sm, _fmt_tokens(tokens) + " tokens", y, TEXT)
    y += 18
    disp.center_text(tft, font_sm, "{}/{} msgs".format(msgs, msg_limit), y, TEXT)
    y += 18
    disp.center_text(tft, font_sm, "{:.0f} tok/min".format(burn), y, TEXT_DIM)
    y += 18
    disp.center_text(tft, font_sm, _fmt_time(remaining) + " left", y, TEXT_DIM)


def _draw_tokens_screen(tft, data):
    """Screen 1: Token breakdown with bars."""
    s = data.get("session", {})

    disp.center_text(tft, font_sm, "TOKENS", 38, ACCENT)

    items = [
        ("Input", s.get("input_tokens", 0)),
        ("Output", s.get("output_tokens", 0)),
        ("Cache W", s.get("cache_write_tokens", 0)),
        ("Cache R", s.get("cache_read_tokens", 0)),
    ]

    # Find max for bar scaling
    max_val = max((v for _, v in items), default=1)
    if max_val == 0:
        max_val = 1

    bar_x = 30
    bar_max_w = 120
    label_x = 30
    value_x = 160
    y = 62

    for label, val in items:
        tft.text(font_sm, label, label_x, y, TEXT_DIM)
        # Bar
        bar_y = y + 16
        frac = val / max_val
        bar_color = ACCENT if val > 0 else 0x2104
        disp.draw_hbar(tft, bar_x, bar_y, bar_max_w, frac, 6, bar_color)
        # Value
        tft.text(font_sm, _fmt_tokens(val), value_x, y, TEXT)
        y += 32

    # Daily summary
    d = data.get("daily", {})
    y += 4
    tft.fill_rect(40, y, 160, 1, 0x4208)  # separator
    y += 8
    disp.center_text(
        tft, font_sm,
        "Today: " + _fmt_cost(d.get("cost_usd", 0)),
        y, ACCENT,
    )


def _draw_models_screen(tft, data):
    """Screen 2: Per-model cost breakdown."""
    models = data.get("models", {})

    disp.center_text(tft, font_sm, "MODELS", 38, ACCENT)

    if not models:
        disp.center_text(tft, font_sm, "No activity", 110, TEXT_DIM)
        return

    y = 62
    label_x = 24
    cost_x = 150

    # Sort by cost descending
    sorted_models = sorted(models.items(), key=lambda kv: kv[1]["cost"], reverse=True)

    for name, stats in sorted_models[:5]:  # max 5 models
        short = _shorten_model(name)
        tft.text(font_sm, short, label_x, y, TEXT)
        tft.text(font_sm, _fmt_cost(stats["cost"]), cost_x, y, ACCENT)
        # Token count below
        y += 16
        tok_str = "  i:{} o:{}".format(
            _fmt_tokens(stats.get("input", 0)),
            _fmt_tokens(stats.get("output", 0)),
        )
        tft.text(font_sm, tok_str, label_x, y, TEXT_DIM)
        y += 22

    # Total
    total_cost = sum(m["cost"] for m in models.values())
    y = max(y + 4, 185)
    tft.fill_rect(40, y, 160, 1, 0x4208)
    y += 8
    disp.center_text(tft, font_sm, "Total " + _fmt_cost(total_cost), y, TEXT)


def _shorten_model(name):
    """'claude-sonnet-4-20250514' -> 'sonnet-4'."""
    parts = name.replace("claude-", "").split("-")
    if len(parts) >= 2:
        result = parts[0]
        for p in parts[1:]:
            if len(p) <= 3:
                result += "-" + p
        return result
    return name[:15]
