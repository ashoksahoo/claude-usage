#!/usr/bin/env python3
"""Claude Code Usage Relay Server.

Reads JSONL logs from ~/.claude/projects/ and serves usage metrics
over HTTP for the ESP32-C3 round display to consume.

Usage:
    python server.py --port 8265 --plan pro
    python server.py --plan max5 --host 0.0.0.0
"""

import json
import os
import sys
import time
import argparse
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude" / "projects"

SESSION_WINDOW = timedelta(hours=5)

# Per-session (5h window) limits by plan — empirical values from claude-monitor
PLAN_LIMITS = {
    "pro": {"tokens": 19_000, "cost": 18.0, "messages": 250},
    "max5": {"tokens": 88_000, "cost": 35.0, "messages": 1_000},
    "max20": {"tokens": 220_000, "cost": 140.0, "messages": 2_000},
}

# USD per million tokens
PRICING = {
    "opus": {"input": 15.0, "output": 75.0, "cache_write": 18.75, "cache_read": 1.5},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.3},
    "haiku": {"input": 0.25, "output": 1.25, "cache_write": 0.3, "cache_read": 0.03},
}

# Simple in-memory cache
_cache: dict = {"data": None, "expires": 0.0}
CACHE_TTL = 5  # seconds


def model_family(model_name: str) -> str:
    m = model_name.lower()
    if "opus" in m:
        return "opus"
    if "haiku" in m:
        return "haiku"
    return "sonnet"


def compute_cost(model: str, inp: int, out: int, cw: int, cr: int) -> float:
    p = PRICING.get(model_family(model), PRICING["sonnet"])
    return (
        inp * p["input"] / 1_000_000
        + out * p["output"] / 1_000_000
        + cw * p["cache_write"] / 1_000_000
        + cr * p["cache_read"] / 1_000_000
    )


def parse_jsonl_files(cutoff: datetime) -> list[dict]:
    """Parse JSONL log files and return assistant entries after cutoff."""
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

                    if obj.get("type") != "assistant":
                        continue

                    msg = obj.get("message") or {}
                    msg_id = msg.get("id", "")
                    if not msg_id or msg_id in seen:
                        continue
                    seen.add(msg_id)

                    ts_str = obj.get("timestamp", "")
                    if not ts_str:
                        continue
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        continue

                    if ts < cutoff:
                        continue

                    usage = msg.get("usage") or {}
                    model = msg.get("model", "unknown")
                    inp = usage.get("input_tokens", 0)
                    out = usage.get("output_tokens", 0)
                    cw = usage.get("cache_creation_input_tokens", 0)
                    cr = usage.get("cache_read_input_tokens", 0)

                    cost = obj.get("costUSD")
                    if cost is None:
                        cost = compute_cost(model, inp, out, cw, cr)

                    entries.append(
                        {
                            "ts": ts,
                            "model": model,
                            "input": inp,
                            "output": out,
                            "cache_write": cw,
                            "cache_read": cr,
                            "cost": float(cost),
                        }
                    )
        except (OSError, PermissionError):
            continue

    entries.sort(key=lambda e: e["ts"])
    return entries


def compute_metrics(plan_name: str) -> dict:
    now = datetime.now(timezone.utc)
    limits = PLAN_LIMITS.get(plan_name, PLAN_LIMITS["pro"])

    session_cutoff = now - SESSION_WINDOW
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = min(session_cutoff, day_start)

    entries = parse_jsonl_files(cutoff)

    session = [e for e in entries if e["ts"] >= session_cutoff]
    daily = [e for e in entries if e["ts"] >= day_start]

    # Session aggregates
    s_inp = sum(e["input"] for e in session)
    s_out = sum(e["output"] for e in session)
    s_cw = sum(e["cache_write"] for e in session)
    s_cr = sum(e["cache_read"] for e in session)
    s_cost = sum(e["cost"] for e in session)
    s_total = s_inp + s_out + s_cw + s_cr

    # Burn rate
    burn_rate = 0.0
    cost_rate = 0.0
    if len(session) >= 2:
        dt_min = (session[-1]["ts"] - session[0]["ts"]).total_seconds() / 60
        if dt_min > 0:
            burn_rate = s_total / dt_min
            cost_rate = s_cost / dt_min

    # Per-model
    models: dict[str, dict] = {}
    for e in session:
        m = e["model"]
        if m not in models:
            models[m] = {"input": 0, "output": 0, "cost": 0.0}
        models[m]["input"] += e["input"]
        models[m]["output"] += e["output"]
        models[m]["cost"] += e["cost"]

    # Round model costs
    for v in models.values():
        v["cost"] = round(v["cost"], 4)

    # Session time remaining
    if session:
        session_end = session[0]["ts"] + SESSION_WINDOW
        remaining = max(0.0, (session_end - now).total_seconds() / 60)
    else:
        remaining = SESSION_WINDOW.total_seconds() / 60

    # Daily aggregates
    d_cost = sum(e["cost"] for e in daily)
    d_tokens = sum(e["input"] + e["output"] + e["cache_write"] + e["cache_read"] for e in daily)

    return {
        "session": {
            "cost_usd": round(s_cost, 4),
            "cost_limit": limits["cost"],
            "tokens_used": s_total,
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
    plan: str = "pro"

    def do_GET(self):
        if self.path == "/api/usage":
            data = get_metrics_cached(self.plan)
            body = json.dumps(data, default=str).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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
        pass  # suppress default logging


def main():
    parser = argparse.ArgumentParser(description="Claude Usage Relay Server")
    parser.add_argument("--port", type=int, default=8265)
    parser.add_argument("--plan", choices=list(PLAN_LIMITS.keys()), default="pro")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    Handler.plan = args.plan

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Claude Usage Relay Server")
    print(f"  Plan:     {args.plan}")
    print(f"  Listen:   http://{args.host}:{args.port}")
    print(f"  Endpoint: http://<your-ip>:{args.port}/api/usage")
    print(f"  Logs:     {CLAUDE_DIR}")
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()


if __name__ == "__main__":
    main()
