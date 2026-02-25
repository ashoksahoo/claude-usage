"""Battery voltage and percentage via ADC on GPIO2 (D0).

The Round Display's voltage divider halves the battery voltage.
KE switch must be closed (default) for this to work.
"""

from machine import ADC, Pin

_adc = ADC(Pin(2))
_adc.atten(ADC.ATTN_11DB)  # 0-3.3V range

# LiPo discharge curve (voltage -> %) — piecewise linear
_CURVE = (
    (4.20, 100),
    (4.06, 90),
    (3.98, 80),
    (3.92, 70),
    (3.87, 60),
    (3.82, 50),
    (3.79, 40),
    (3.77, 30),
    (3.74, 20),
    (3.68, 10),
    (3.45, 5),
    (3.00, 0),
)


def voltage():
    """Read battery voltage in volts."""
    raw = _adc.read()
    return (raw / 4095) * 3.3 * 2


def percent():
    """Estimate battery percentage from voltage (0-100)."""
    v = voltage()
    if v >= _CURVE[0][0]:
        return 100
    if v <= _CURVE[-1][0]:
        return 0
    for i in range(len(_CURVE) - 1):
        v_hi, p_hi = _CURVE[i]
        v_lo, p_lo = _CURVE[i + 1]
        if v >= v_lo:
            frac = (v - v_lo) / (v_hi - v_lo)
            return int(p_lo + frac * (p_hi - p_lo))
    return 0
