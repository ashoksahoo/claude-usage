"""PCF8563 RTC driver for the Seeed Round Display.

I2C address: 0x51
Shares I2C bus with touch controller (CHSC6X at 0x2E).
"""

from micropython import const

_ADDR = const(0x51)


class PCF8563:
    def __init__(self, i2c):
        self.i2c = i2c

    @staticmethod
    def _bcd2dec(bcd):
        return (bcd >> 4) * 10 + (bcd & 0x0F)

    @staticmethod
    def _dec2bcd(dec):
        return ((dec // 10) << 4) | (dec % 10)

    def datetime(self, dt=None):
        """Get or set datetime.

        Format: (year, month, day, weekday, hour, minute, second)
        Year is 2-digit (e.g., 26 for 2026). Weekday: 0=Sunday.
        """
        if dt is None:
            data = self.i2c.readfrom_mem(_ADDR, 0x02, 7)
            return (
                self._bcd2dec(data[6]),         # year
                self._bcd2dec(data[5] & 0x1F),  # month
                self._bcd2dec(data[3] & 0x3F),  # day
                data[4] & 0x07,                 # weekday
                self._bcd2dec(data[2] & 0x3F),  # hour
                self._bcd2dec(data[1] & 0x7F),  # minute
                self._bcd2dec(data[0] & 0x7F),  # second
            )
        buf = bytearray(7)
        buf[0] = self._dec2bcd(dt[6])  # second
        buf[1] = self._dec2bcd(dt[5])  # minute
        buf[2] = self._dec2bcd(dt[4])  # hour
        buf[3] = self._dec2bcd(dt[2])  # day
        buf[4] = dt[3]                 # weekday
        buf[5] = self._dec2bcd(dt[1])  # month
        buf[6] = self._dec2bcd(dt[0])  # year
        self.i2c.writeto_mem(_ADDR, 0x02, buf)
