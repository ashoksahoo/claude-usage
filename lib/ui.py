"""UI screens for the round display.

Four screens, navigated by touch (tap left=prev, tap right=next):
  0: Dashboard — session / weekly / sonnet utilization bars (from Anthropic API)
  1: Clock — digital clock with date, battery + voltage
  2: Token breakdown with bars
  3: Per-model cost breakdown
"""

from micropython import const
import lib.display as disp
import lib.battery as battery
from lib.colors import (
    BG, TEXT, TEXT_DIM, ACCENT, ACCENT_DIM,
    GOOD, WARN, BAD, BAR_FILL, BAR_BG,
)

# Loaded by main.py after display init
font_lg = None  # vga1_bold_16x32 or vga1_16x32
font_sm = None  # vga1_8x16

NUM_SCREENS = 4
_CX = const(120)
_CY = const(120)


# ── Formatters ──

def _fmt_tokens(n):
    if n >= 1_000_000:
        return "{:.2f}M".format(n / 1_000_000)
    if n >= 1_000:
        return "{:.1f}K".format(n / 1_000)
    return str(n)


def _fmt_cost(c):
    return "${:.2f}".format(c)


def _fmt_time(minutes):
    h = int(minutes // 60)
    m = int(minutes % 60)
    if h > 0:
        return "{}h {:02d}m".format(h, m)
    return "{}m".format(m)


# ── Drawing primitives ──

def _bar_color(pct):
    """Color for progress bar fill based on percentage."""
    if pct < 50:
        return BAR_FILL
    if pct < 80:
        return WARN
    return BAD


def _draw_progress_bar(tft, x, y, w, h, pct):
    """Draw a rounded progress bar with background."""
    # Background
    tft.fill_rect(x, y, w, h, BAR_BG)
    # Fill
    fill_w = int(w * min(pct / 100, 1.0))
    if fill_w > 0:
        tft.fill_rect(x, y, fill_w, h, _bar_color(pct))


def _draw_widget(tft, y, label, value_str, pct, subtitle):
    """Draw a labeled progress bar widget."""
    lx = 35
    # Label
    tft.text(font_sm, label, lx, y, TEXT)
    # Value right-aligned
    vw = len(value_str) * font_sm.WIDTH
    tft.text(font_sm, value_str, 205 - vw, y, TEXT)
    # Progress bar
    _draw_progress_bar(tft, lx, y + 17, 170, 7, pct)
    # Subtitle
    tft.text(font_sm, subtitle, lx, y + 28, TEXT_DIM)



def _draw_dots(tft, current, total):
    """Draw page indicator dots at the bottom."""
    dot_w = 6
    gap = 5
    total_w = total * dot_w + (total - 1) * gap
    x = (_CX * 2 - total_w) // 2
    y = 222

    for i in range(total):
        c = ACCENT if i == current else 0x4208
        tft.fill_rect(x + i * (dot_w + gap), y, dot_w, 3, c)


# ── Screen renderer ──

def draw_screen(tft, screen_idx, data):
    """Render the specified screen with usage data."""
    disp.clear(tft)

    if data is None:
        disp.center_text(tft, font_sm, "No Data", 108, TEXT_DIM)
        _draw_dots(tft, screen_idx, NUM_SCREENS)
        return

    if screen_idx == 0:
        _draw_dashboard(tft, data)
    elif screen_idx == 1:
        _draw_clock_screen(tft, data)
    elif screen_idx == 2:
        _draw_tokens_screen(tft, data)
    elif screen_idx == 3:
        _draw_models_screen(tft, data)

    _draw_dots(tft, screen_idx, NUM_SCREENS)


# ── Screen 0: Dashboard ──

def _draw_dashboard(tft, data):
    """Dashboard: Session / Weekly / Sonnet bars from Anthropic usage API."""
    u = data.get("utilization", {})

    # Plan header
    plan = data.get("plan", "")
    plan_label = plan.upper() if plan else ""
    disp.center_text(tft, font_sm, plan_label, 24, ACCENT)

    # Session bar (five_hour utilization)
    sess = u.get("session", {})
    s_pct = sess.get("pct", 0)
    s_reset = sess.get("reset_label", "")
    _draw_widget(
        tft, 46,
        "Session",
        "{}%".format(s_pct),
        s_pct,
        "Resets {}".format(s_reset) if s_reset else "",
    )

    # Separator
    tft.fill_rect(50, 92, 140, 1, 0x3186)

    # Weekly bar (seven_day utilization)
    week = u.get("weekly", {})
    w_pct = week.get("pct", 0)
    w_reset = week.get("reset_label", "")
    _draw_widget(
        tft, 100,
        "Weekly",
        "{}%".format(w_pct),
        w_pct,
        "Resets {}".format(w_reset) if w_reset else "",
    )

    # Separator
    tft.fill_rect(50, 146, 140, 1, 0x3186)

    # Sonnet bar (seven_day_sonnet utilization)
    son = u.get("sonnet", {})
    sn_pct = son.get("pct", 0)
    sn_reset = son.get("reset_label", "")
    _draw_widget(
        tft, 154,
        "Sonnet",
        "{}%".format(sn_pct),
        sn_pct,
        "Resets {}".format(sn_reset) if sn_reset else "",
    )


# ── Screen 1: Clock ──

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _draw_clock_screen(tft, data):
    """Digital clock with date, pulled from relay server's system time."""
    c = data.get("clock", {})
    if not c:
        disp.center_text(tft, font_sm, "No clock data", 110, TEXT_DIM)
        return

    hour = c.get("hour", 0)
    minute = c.get("minute", 0)
    day = c.get("day", 1)
    month = c.get("month", 1)
    year = c.get("year", 2026)
    weekday = c.get("weekday", 0)

    # Time — large centered
    time_str = "{:02d}:{:02d}".format(hour, minute)
    disp.center_text(tft, font_lg, time_str, 88, TEXT)

    # Date — below time
    date_str = "{} {} {}, {}".format(
        _WEEKDAYS[weekday], _MONTHS[month], day, year
    )
    disp.center_text(tft, font_sm, date_str, 130, TEXT_DIM)

    # Daily cost summary
    d = data.get("daily", {})
    d_cost = d.get("cost_usd", 0)
    if d_cost > 0:
        disp.center_text(tft, font_sm, "Today: " + _fmt_cost(d_cost), 158, ACCENT)

    # Battery + voltage centered
    pct = battery.percent()
    volts = battery.voltage()
    if pct > 60:
        batt_color = GOOD
    elif pct > 20:
        batt_color = WARN
    else:
        batt_color = BAD
    batt_str = "{}%  {:.2f}V".format(pct, volts)
    disp.center_text(tft, font_sm, batt_str, 190, batt_color)


# ── Screen 2: Token Breakdown ──

def _draw_tokens_screen(tft, data):
    s = data.get("session", {})

    disp.center_text(tft, font_sm, "TOKENS", 38, ACCENT)

    items = [
        ("Input", s.get("input_tokens", 0)),
        ("Output", s.get("output_tokens", 0)),
        ("Cache W", s.get("cache_write_tokens", 0)),
        ("Cache R", s.get("cache_read_tokens", 0)),
    ]

    max_val = max((v for _, v in items), default=1)
    if max_val == 0:
        max_val = 1

    y = 62
    for label, val in items:
        tft.text(font_sm, label, 30, y, TEXT_DIM)
        bar_y = y + 16
        frac = val / max_val
        bar_color = ACCENT if val > 0 else 0x2104
        disp.draw_hbar(tft, 30, bar_y, 120, frac, 6, bar_color)
        tft.text(font_sm, _fmt_tokens(val), 160, y, TEXT)
        y += 32

    d = data.get("daily", {})
    y += 4
    tft.fill_rect(40, y, 160, 1, 0x4208)
    y += 8
    disp.center_text(tft, font_sm, "Today: " + _fmt_cost(d.get("cost_usd", 0)), y, ACCENT)


# ── Screen 3: Models ──

def _draw_models_screen(tft, data):
    models = data.get("models", {})

    disp.center_text(tft, font_sm, "MODELS", 38, ACCENT)

    if not models:
        disp.center_text(tft, font_sm, "No activity", 110, TEXT_DIM)
        return

    y = 62
    sorted_models = sorted(models.items(), key=lambda kv: kv[1]["cost"], reverse=True)

    for name, stats in sorted_models[:5]:
        short = _shorten_model(name)
        tft.text(font_sm, short, 24, y, TEXT)
        tft.text(font_sm, _fmt_cost(stats["cost"]), 150, y, ACCENT)
        y += 16
        tok_str = "  i:{} o:{}".format(
            _fmt_tokens(stats.get("input", 0)),
            _fmt_tokens(stats.get("output", 0)),
        )
        tft.text(font_sm, tok_str, 24, y, TEXT_DIM)
        y += 22

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
