"""RGB565 color constants for the round display UI."""

from micropython import const

# Basic colors
BLACK = const(0x0000)
WHITE = const(0xFFFF)
RED = const(0xF800)
GREEN = const(0x07E0)
BLUE = const(0x001F)
YELLOW = const(0xFFE0)
CYAN = const(0x07FF)

# UI palette
BG = const(0x0000)           # Screen background (black)
TEXT = const(0xFFFF)          # Primary text (white)
TEXT_DIM = const(0x7BEF)     # Dimmed text (gray)
ACCENT = const(0xFD20)       # Warm orange (Claude-ish)
ACCENT_DIM = const(0x7A40)   # Dimmed orange
GOOD = const(0x07E0)         # Green - under budget
WARN = const(0xFFE0)         # Yellow - approaching budget
BAD = const(0xF800)          # Red - over budget

# Cost tier thresholds (USD)
COST_TIER_LOW = 10.0
COST_TIER_MED = 30.0


def cost_color(amount, budget):
    """Return color based on cost relative to budget."""
    if budget <= 0:
        return TEXT
    ratio = amount / budget
    if ratio < 0.5:
        return GOOD
    elif ratio < 0.8:
        return WARN
    else:
        return BAD
