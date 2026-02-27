"""Weather data fetcher using Open-Meteo (free, no API key required).

Zero external dependencies — uses stdlib urllib only.

Flow:
  1. If no location given, auto-detect via GeoIP (ip-api.com)
  2. Geocode city name → lat/lon  (Open-Meteo geocoding API)
  3. Fetch current weather         (Open-Meteo forecast API)
  4. Cache result in-memory for 2 hours
"""

import json
import ssl
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

GEO_URL   = "https://geocoding-api.open-meteo.com/v1/search"
WX_URL    = "https://api.open-meteo.com/v1/forecast"
GEOIP_URL = "http://ip-api.com/json/?fields=status,city,country,lat,lon"

CACHE_TTL = 2 * 3600  # 2 hours

# WMO weather interpretation codes → plain English description
WMO_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "icy fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 75: "heavy snow",
    77: "snow grains",
    80: "showers", 81: "showers", 82: "heavy showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm w/hail", 99: "severe thunderstorm",
}

# 3-char ASCII icons for bitmap font display on the device
WMO_ICONS = {
    0:  "SUN",
    1:  "SUN", 2:  "FEW", 3:  "OVC",
    45: "FOG", 48: "FOG",
    51: "DZL", 53: "DZL", 55: "DZL",
    61: "RAN", 63: "RAN", 65: "RAN",
    71: "SNW", 73: "SNW", 75: "SNW", 77: "SNW",
    80: "SHR", 81: "SHR", 82: "SHR",
    85: "SNS", 86: "SNS",
    95: "STM", 96: "STM", 99: "STM",
}

_cache: dict = {"data": None, "expires": 0.0, "location": None}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ssl_context() -> ssl.SSLContext:
    """Return an SSL context that works on macOS system Python (no certifi needed).

    macOS Python from python.org ships without root CAs; /etc/ssl/cert.pem
    contains the system trust store and works as a reliable fallback.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        pass
    for ca_file in ["/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"]:
        if Path(ca_file).exists():
            return ssl.create_default_context(cafile=ca_file)
    return ssl.create_default_context()


_CTX = _ssl_context()


def _fetch_json(url: str, params: dict | None = None, timeout: int = 8) -> dict:
    if params:
        url = f"{url}?{urlencode(params)}"
    with urllib.request.urlopen(url, timeout=timeout, context=_CTX) as resp:
        return json.loads(resp.read().decode())


def _geoip_location() -> dict | None:
    """Estimate location from public IP using ip-api.com (free, no key).

    Returns {city, country, lat, lon} or None on failure.
    """
    try:
        data = _fetch_json(GEOIP_URL)
        if data.get("status") == "success":
            return {
                "city":    data.get("city", ""),
                "country": data.get("country", ""),
                "lat":     data["lat"],
                "lon":     data["lon"],
            }
    except Exception as e:
        print(f"[weather] GeoIP failed: {e}")
    return None


def _geocode(city: str) -> dict | None:
    """Geocode city name → {lat, lon, name, country} or None."""
    try:
        data = _fetch_json(GEO_URL, {"name": city, "count": 1})
        results = data.get("results")
        if results:
            r = results[0]
            return {
                "lat":     r["latitude"],
                "lon":     r["longitude"],
                "name":    r["name"],
                "country": r.get("country", ""),
            }
    except Exception as e:
        print(f"[weather] Geocode failed for '{city}': {e}")
    return None


def _fetch_current(lat: float, lon: float) -> dict | None:
    """Fetch current conditions from Open-Meteo for given coordinates."""
    params = {
        "latitude":         lat,
        "longitude":        lon,
        "current":          "temperature_2m,weathercode,windspeed_10m,relative_humidity_2m",
        "temperature_unit": "celsius",
        "windspeed_unit":   "kmh",
        "timezone":         "auto",
    }
    try:
        data = _fetch_json(WX_URL, params)
        return data.get("current", {})
    except Exception as e:
        print(f"[weather] Forecast fetch failed: {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def get_weather(location: str | None = None) -> dict:
    """Return current weather, cached for 2 hours.

    Args:
        location: City name (e.g. "London") or None to auto-detect via GeoIP.

    Returns on success:
        {
            "temp_c":    22.4,
            "wmo":       2,
            "condition": "partly cloudy",
            "icon":      "FEW",     # 3-char ASCII for device bitmap font
            "city":      "London, United Kingdom",
        }
    Returns on failure:
        {"error": "<reason>"}
    """
    now = time.monotonic()
    if (_cache["data"] is not None
            and now < _cache["expires"]
            and _cache["location"] == location):
        return _cache["data"]

    result = _do_fetch(location)
    _cache["data"] = result
    _cache["expires"] = now + CACHE_TTL
    _cache["location"] = location
    return result


def _do_fetch(location: str | None) -> dict:
    # ── Resolve coordinates ──────────────────────────────────────────────────
    if location:
        geo = _geocode(location)
        if geo is None:
            return {"error": f"Location '{location}' not found"}
        lat, lon = geo["lat"], geo["lon"]
        city_label = f"{geo['name']}, {geo['country']}"
    else:
        geo = _geoip_location()
        if geo is None:
            return {"error": "Could not determine location (GeoIP failed)"}
        lat, lon = geo["lat"], geo["lon"]
        city_label = f"{geo['city']}, {geo['country']}"

    # ── Fetch weather ────────────────────────────────────────────────────────
    current = _fetch_current(lat, lon)
    if current is None:
        return {"error": "Weather fetch failed"}

    code = current.get("weathercode", 0)
    return {
        "temp_c":    current.get("temperature_2m"),
        "wmo":       code,
        "condition": WMO_DESCRIPTIONS.get(code, f"code {code}"),
        "icon":      WMO_ICONS.get(code, "???"),
        "city":      city_label,
    }
