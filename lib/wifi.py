"""WiFi connection management for ESP32-C3."""

import network
import time

# Lower TX power to reduce current spikes on battery (default 20dBm).
# 13dBm is enough for same-room range and cuts peak draw significantly.
_TX_POWER_DBM = 13


def connect(ssid, password, timeout=20):
    """Connect to WiFi. Returns the WLAN interface.

    Raises RuntimeError on timeout.
    """
    wlan = network.WLAN(network.STA_IF)

    # Full radio reset to clear stale state (helps after power glitch)
    wlan.active(False)
    time.sleep(1)
    wlan.active(True)
    time.sleep(0.5)

    # Reduce TX power before connecting — less current draw on battery
    try:
        wlan.config(txpower=_TX_POWER_DBM)
    except Exception:
        pass

    if wlan.isconnected():
        return wlan

    wlan.connect(ssid, password)
    start = time.time()
    while not wlan.isconnected():
        if time.time() - start > timeout:
            wlan.active(False)
            raise RuntimeError("WiFi timeout")
        time.sleep(0.5)

    return wlan


def ensure_connected(wlan, ssid, password):
    """Reconnect if disconnected. Returns True if connected."""
    if wlan.isconnected():
        return True
    try:
        wlan.active(False)
        time.sleep(1)
        connect(ssid, password)
        return True
    except RuntimeError:
        return False


def ip(wlan):
    """Return current IP address string."""
    return wlan.ifconfig()[0] if wlan.isconnected() else None
