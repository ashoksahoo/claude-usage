"""CHSC6X capacitive touch driver for the Seeed Round Display.

I2C address: 0x2E
Interrupt pin: GPIO20 (D7) - active LOW when touched.
Shares I2C bus with RTC (PCF8563 at 0x51).
"""

from machine import Pin
from micropython import const

_ADDR = const(0x2E)


class Touch:
    def __init__(self, i2c, int_pin=20):
        self.i2c = i2c
        self.int = Pin(int_pin, Pin.IN, Pin.PULL_UP)

    def is_touched(self):
        return self.int.value() == 0

    def read(self):
        """Read touch point. Returns (x, y) or None."""
        if not self.is_touched():
            return None
        try:
            data = self.i2c.readfrom(_ADDR, 5)
            x = (data[1] << 8) | data[2]
            y = (data[3] << 8) | data[4]
            return (min(max(x, 0), 239), min(max(y, 0), 239))
        except OSError:
            return None
