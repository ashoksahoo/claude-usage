#!/usr/bin/env python3
"""Claude Code Usage Relay Server.

Fetches real-time utilization from Anthropic's OAuth usage API (same
approach as TokenEater) and supplements with JSONL-derived detail data
for the cost/token/model screens.

Usage:
    python server.py                      # auto-detect plan, use OAuth API
    python server.py --plan max5
    python server.py --no-api             # JSONL-only fallback
"""

import json
import subprocess
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from weather import get_weather

CLAUDE_DIR = Path.home() / ".claude" / "projects"
SETTINGS_FILE = Path.home() / ".claude" / "settings.json"

SESSION_HOURS = 5
WEEK_WINDOW = timedelta(days=7)

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Per-session limits by plan — empirical values from claude-monitor
PLAN_LIMITS = {
    "pro": {"cost": 18.0, "messages": 250, "tokens": 19_000},
    "max5": {"cost": 35.0, "messages": 1_000, "tokens": 88_000},
    "max20": {"cost": 140.0, "messages": 2_000, "tokens": 220_000},
}

# USD per million tokens (from LiteLLM, matching ccusage)
PRICING = {
    "opus-4":   {"input": 15.0, "output": 75.0,  "cache_write": 18.75, "cache_read": 1.5},
    "opus-4-6": {"input": 5.0,  "output": 25.0,  "cache_write": 6.25,  "cache_read": 0.5},
    "sonnet":   {"input": 3.0,  "output": 15.0,  "cache_write": 3.75,  "cache_read": 0.3},
    "haiku":    {"input": 0.25, "output": 1.25,   "cache_write": 0.3,   "cache_read": 0.03},
}

_cache: dict = {"data": None, "expires": 0.0}
CACHE_TTL = 300  # 5 minutes

# ── OAuth / Anthropic Usage API ──

USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_API_BETA = "oauth-2025-04-20"

_token_cache: dict = {
    "access_token": None, "expires_at": 0,
    "subscription_type": None, "rate_limit_tier": None,
}
_usage_api_cache: dict = {"data": None, "expires": 0.0}
USAGE_API_CACHE_TTL = 30

_use_api: bool = True


def get_oauth_credentials() -> dict:
    """Read Claude Code OAuth credentials.

    Checks ~/.claude/.credentials.json first (TokenEater v4.3.0 approach),
    falling back to macOS Keychain only when needed.
    """
    # 1. Try credentials file (no password prompt, works on all platforms)
    creds_file = Path.home() / ".claude" / ".credentials.json"
    try:
        if creds_file.exists():
            creds = json.loads(creds_file.read_text())
            oauth = creds.get("claudeAiOauth", {})
            if oauth.get("accessToken"):
                return oauth
    except (json.JSONDecodeError, OSError):
        pass

    # 2. Fall back to macOS Keychain
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return {}
        creds = json.loads(result.stdout.strip())
        return creds.get("claudeAiOauth", {})
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return {}


def get_access_token() -> str | None:
    """Get a valid OAuth access token, re-reading Keychain when near expiry."""
    now_ms = int(time.time() * 1000)

    # Return cached token if still valid (60s buffer)
    if (_token_cache["access_token"]
            and _token_cache["expires_at"] > now_ms + 60_000):
        return _token_cache["access_token"]

    # Re-read from Keychain (Claude Code handles token refresh)
    oauth = get_oauth_credentials()
    if not oauth or not oauth.get("accessToken"):
        return None

    _token_cache["access_token"] = oauth["accessToken"]
    _token_cache["expires_at"] = oauth.get("expiresAt", 0)
    _token_cache["subscription_type"] = oauth.get("subscriptionType")
    _token_cache["rate_limit_tier"] = oauth.get("rateLimitTier")
    return _token_cache["access_token"]


def fetch_usage_api() -> dict | None:
    """Fetch utilization from Anthropic's OAuth usage API.

    Uses curl subprocess to avoid Python SSL cert issues on macOS.
    Returns raw API response dict or None. Uses 30s cache.
    """
    if not _use_api:
        return None

    now = time.monotonic()
    if _usage_api_cache["data"] is not None and now < _usage_api_cache["expires"]:
        return _usage_api_cache["data"]

    token = get_access_token()
    if not token:
        return _usage_api_cache.get("data")  # stale is better than nothing

    try:
        result = subprocess.run(
            [
                "curl", "-s", "--max-time", "10",
                "-H", f"Authorization: Bearer {token}",
                "-H", f"anthropic-beta: {USAGE_API_BETA}",
                USAGE_API_URL,
            ],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        data = json.loads(result.stdout)
        _usage_api_cache["data"] = data
        _usage_api_cache["expires"] = now + USAGE_API_CACHE_TTL
        return data
    except Exception as e:
        print(f"Usage API error: {e}")
        return _usage_api_cache.get("data")


def _format_reset_time(resets_at: str) -> str:
    """Format ISO resets_at timestamp — relative delta + local clock time."""
    try:
        reset_dt = datetime.fromisoformat(resets_at)
        now = datetime.now(timezone.utc)
        total_min = (reset_dt - now).total_seconds() / 60
        local_time = reset_dt.astimezone().strftime("%H:%M")

        if total_min <= 0:
            return "now"
        if total_min < 300:  # < 5 hours — show delta + clock
            h = int(total_min // 60)
            m = int(total_min % 60)
            delta = f"{h}h{m:02d}m" if h > 0 else f"{m}m"
            return f"{delta} @{local_time}"
        return f"{_DAY_NAMES[reset_dt.weekday()]} @{local_time}"
    except (ValueError, TypeError):
        return ""


def build_utilization(api_data: dict | None) -> dict:
    """Transform raw API response into clean utilization dict for the ESP."""
    empty = {"pct": 0, "reset_label": ""}

    if api_data is None:
        return {"session": empty, "weekly": empty, "sonnet": empty}

    result = {}
    for key, api_key in [("session", "five_hour"), ("weekly", "seven_day"), ("sonnet", "seven_day_sonnet")]:
        bucket = api_data.get(api_key)
        if bucket:
            result[key] = {
                "pct": round(bucket.get("utilization", 0)),
                "reset_label": _format_reset_time(bucket.get("resets_at", "")),
            }
        else:
            result[key] = dict(empty)

    return result


# ── Plan detection ──

def detect_plan() -> str:
    """Auto-detect plan from OAuth token metadata, falling back to settings.json."""
    oauth = get_oauth_credentials()
    if oauth:
        tier = (oauth.get("rateLimitTier") or "").lower()
        sub = (oauth.get("subscriptionType") or "").lower()
        if "max_20x" in tier:
            return "max20"
        if "max" in tier or "max" in sub:
            return "max5"
        if sub == "pro":
            return "pro"

    try:
        with open(SETTINGS_FILE) as f:
            settings = json.load(f)
        if "opus" in settings.get("model", "").lower():
            return "max5"
    except (OSError, json.JSONDecodeError):
        pass
    return "pro"


# ── JSONL parsing (for detail screens) ──

def model_family(model_name: str) -> str:
    m = model_name.lower()
    # Distinguish opus-4-6 (cheaper) from opus-4 (original)
    if "opus-4-6" in m or "opus-4.6" in m:
        return "opus-4-6"
    if "opus" in m:
        return "opus-4"
    if "haiku" in m:
        return "haiku"
    return "sonnet"


def compute_cost(model: str, inp: int, out: int, cw: int, cr: int) -> float:
    """Compute cost from tokens using per-model pricing (fallback when costUSD missing)."""
    p = PRICING.get(model_family(model), PRICING["sonnet"])
    return (
        inp * p["input"] / 1_000_000
        + out * p["output"] / 1_000_000
        + cw * p["cache_write"] / 1_000_000
        + cr * p["cache_read"] / 1_000_000
    )


def parse_jsonl_files(cutoff: datetime) -> list[dict]:
    """Parse JSONL log files matching ccusage's approach.

    Key differences from earlier versions:
      - No type=="assistant" filter (ccusage accepts any entry with usage data)
      - Dedup on message.id:requestId pairs (ccusage style)
      - Prefer costUSD from JSONL, fall back to computed cost
    """
    entries = []
    seen: set[str] = set()
    cutoff_epoch = cutoff.timestamp()

    if not CLAUDE_DIR.exists():
        return entries

    for fpath in CLAUDE_DIR.rglob("*.jsonl"):
        try:
            if fpath.stat().st_mtime < cutoff_epoch:
                continue
        except OSError:
            continue

        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg = obj.get("message") or {}
                    usage = msg.get("usage") or {}

                    # Must have token data
                    inp = usage.get("input_tokens")
                    out = usage.get("output_tokens")
                    if inp is None or out is None:
                        continue

                    cw = usage.get("cache_creation_input_tokens", 0)
                    cr = usage.get("cache_read_input_tokens", 0)

                    if not any([inp, out, cw, cr]):
                        continue

                    # Dedup: message.id + requestId (matches ccusage)
                    msg_id = msg.get("id")
                    req_id = obj.get("requestId")
                    if msg_id and req_id:
                        dedup_key = f"{msg_id}:{req_id}"
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                    ts_str = obj.get("timestamp", "")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue

                    if ts < cutoff:
                        continue

                    model = msg.get("model", "unknown")

                    # Prefer costUSD from JSONL (matches ccusage auto mode)
                    cost = obj.get("costUSD")
                    if cost is None:
                        cost = compute_cost(model, inp, out, cw, cr)

                    entries.append({
                        "ts": ts, "model": model,
                        "input": inp, "output": out,
                        "cache_write": cw, "cache_read": cr,
                        "cost": float(cost),
                    })
        except (OSError, PermissionError):
            continue

    entries.sort(key=lambda e: e["ts"])
    return entries


def _pct(used: float, limit: float) -> int:
    if limit <= 0:
        return 0
    return min(100, round(used / limit * 100))


def _find_active_session(entries: list[dict], now: datetime) -> tuple[list[dict], float]:
    """Find the active session block (hour-rounded anchor + 5h)."""
    ten_h_ago = now - timedelta(hours=10)
    recent = [e for e in entries if e["ts"] >= ten_h_ago]
    if not recent:
        return [], SESSION_HOURS * 60

    blocks: list[dict] = []
    cur: dict | None = None

    for entry in recent:
        if cur is None or entry["ts"] > cur["end"]:
            if cur is not None:
                blocks.append(cur)
            start = entry["ts"].replace(minute=0, second=0, microsecond=0)
            end = start + timedelta(hours=SESSION_HOURS)
            cur = {"start": start, "end": end, "entries": [entry]}
        else:
            cur["entries"].append(entry)

    if cur is not None:
        blocks.append(cur)

    for block in reversed(blocks):
        if block["end"] > now:
            remaining = max(0.0, (block["end"] - now).total_seconds() / 60)
            return block["entries"], remaining

    return [], SESSION_HOURS * 60


# ── Metrics computation ──

def compute_metrics(plan_name: str) -> dict:
    now = datetime.now(timezone.utc)
    limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["pro"])

    # Fetch utilization from Anthropic API (primary data for dashboard)
    api_data = fetch_usage_api()
    utilization = build_utilization(api_data)

    # JSONL-derived data for detail screens
    # Use local timezone for day boundary (matches ccusage default)
    local_now = datetime.now().astimezone()
    day_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start = day_start_local.astimezone(timezone.utc)
    cutoff = min(now - timedelta(hours=10), day_start)
    entries = parse_jsonl_files(cutoff)

    session, remaining = _find_active_session(entries, now)

    s_inp = sum(e["input"] for e in session)
    s_out = sum(e["output"] for e in session)
    s_cw = sum(e["cache_write"] for e in session)
    s_cr = sum(e["cache_read"] for e in session)
    s_cost = sum(e["cost"] for e in session)
    s_tokens_display = s_inp + s_out

    burn_rate = 0.0
    cost_rate = 0.0
    if len(session) >= 2:
        dt_min = (session[-1]["ts"] - session[0]["ts"]).total_seconds() / 60
        if dt_min > 0:
            burn_rate = s_tokens_display / dt_min
            cost_rate = s_cost / dt_min

    # Daily
    daily = [e for e in entries if e["ts"] >= day_start]
    d_cost = sum(e["cost"] for e in daily)
    d_tokens = sum(e["input"] + e["output"] + e["cache_write"] + e["cache_read"] for e in daily)

    # Per-model (daily, matching ccusage)
    models: dict[str, dict] = {}
    for e in daily:
        m = e["model"]
        if m not in models:
            models[m] = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0, "cost": 0.0}
        models[m]["input"] += e["input"]
        models[m]["output"] += e["output"]
        models[m]["cache_write"] += e["cache_write"]
        models[m]["cache_read"] += e["cache_read"]
        models[m]["cost"] += e["cost"]
    for v in models.values():
        v["cost"] = round(v["cost"], 4)

    return {
        "utilization": utilization,
        "session": {
            "cost_usd": round(s_cost, 4),
            "cost_limit": limits["cost"],
            "tokens_used": s_tokens_display,
            "token_limit": limits["tokens"],
            "messages_sent": len(session),
            "message_limit": limits["messages"],
            "input_tokens": s_inp,
            "output_tokens": s_out,
            "cache_write_tokens": s_cw,
            "cache_read_tokens": s_cr,
            "burn_rate": round(burn_rate, 1),
            "cost_rate": round(cost_rate, 6),
            "minutes_remaining": round(remaining, 1),
        },
        "daily": {
            "cost_usd": round(d_cost, 4),
            "tokens": d_tokens,
        },
        "models": models,
        "plan": plan_name,
        "ts": now.isoformat(),
    }


def get_metrics_cached(plan_name: str) -> dict:
    now = time.monotonic()
    if _cache["data"] is not None and now < _cache["expires"]:
        return _cache["data"]
    data = compute_metrics(plan_name)
    _cache["data"] = data
    _cache["expires"] = now + CACHE_TTL
    return data


class Handler(BaseHTTPRequestHandler):
    plan: str = "max5"
    location: str | None = None

    def do_GET(self):
        if self.path == "/api/usage":
            data = get_metrics_cached(self.plan)
            # Inject fresh local time (not cached — clock needs real-time)
            local = datetime.now()
            data["clock"] = {
                "hour": local.hour,
                "minute": local.minute,
                "second": local.second,
                "day": local.day,
                "month": local.month,
                "year": local.year,
                "weekday": local.weekday(),
            }
            # Weather is cached 2 hours inside get_weather()
            data["weather"] = get_weather(self.location)
            body = json.dumps(data, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


def main():
    global _use_api

    parser = argparse.ArgumentParser(description="Claude Usage Relay Server")
    parser.add_argument("--port", type=int, default=8265)
    parser.add_argument(
        "--plan", choices=list(PLAN_LIMITS.keys()) + ["auto"], default="auto",
        help="Plan type (pro, max5, max20, auto). auto detects from OAuth/settings.",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument(
        "--no-api", action="store_true",
        help="Disable Anthropic usage API; use JSONL only.",
    )
    parser.add_argument(
        "--location", default=None, metavar="CITY",
        help="City name for weather (e.g. 'London'). Auto-detected via GeoIP if omitted.",
    )
    args = parser.parse_args()

    _use_api = not args.no_api

    plan = args.plan
    if plan == "auto":
        plan = detect_plan()
        print(f"Auto-detected plan: {plan}")

    Handler.plan = plan
    Handler.location = args.location

    # Test OAuth on startup
    if _use_api:
        token = get_access_token()
        if token:
            sub = _token_cache.get("subscription_type") or "unknown"
            tier = _token_cache.get("rate_limit_tier") or "unknown"
            print(f"  OAuth:         connected ({sub} / {tier})")
        else:
            print(f"  OAuth:         NOT FOUND (JSONL fallback)")
            print(f"  Hint:          Ensure Claude Code is logged in")

    # Pre-warm weather cache so first device request is instant
    print(f"Claude Usage Relay Server")
    print(f"  Plan:          {plan}")
    print(f"  API:           {'enabled' if _use_api else 'disabled (JSONL only)'}")
    location_label = args.location if args.location else "auto (GeoIP)"
    print(f"  Weather:       {location_label} (fetching...)", end="", flush=True)
    wx = get_weather(args.location)
    if wx.get("error"):
        print(f" ERROR: {wx['error']}")
    else:
        print(f" {wx['temp_c']}C {wx['condition']} @ {wx['city']}")

    server = HTTPServer((args.host, args.port), Handler)
    print(f"  Listen:        http://{args.host}:{args.port}")
    print(f"  Endpoint:      http://<your-ip>:{args.port}/api/usage")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
