"""Fetch usage metrics from the relay server over local HTTP."""

import gc
import json
import uasyncio as asyncio


async def _do_get(host, port):
    """Async HTTP/1.0 GET /api/usage — yields at every network read."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        req = (
            "GET /api/usage HTTP/1.0\r\nHost: {}:{}\r\nConnection: close\r\n\r\n"
        ).format(host, port).encode()
        writer.write(req)
        await writer.drain()

        # Read until header separator found (256-byte chunks)
        hbuf = b""
        while b"\r\n\r\n" not in hbuf:
            chunk = await reader.read(256)
            if not chunk:
                return None
            hbuf += chunk

        sep = hbuf.find(b"\r\n\r\n")
        headers = hbuf[:sep].decode("ascii", "ignore")
        initial_body = hbuf[sep + 4:]

        # Parse Content-Length for exact-size read
        content_length = None
        for line in headers.splitlines():
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())
                break

        # Collect remaining body into a list then join once (avoids repeated alloc)
        parts = [initial_body]
        remaining = (content_length - len(initial_body)) if content_length else None
        while True:
            if remaining is not None:
                if remaining <= 0:
                    break
                n = min(512, remaining)
            else:
                n = 512
            chunk = await reader.read(n)
            if not chunk:
                break
            parts.append(bytes(chunk))
            if remaining is not None:
                remaining -= len(chunk)

        body = b"".join(parts)
    finally:
        writer.close()

    return json.loads(body)


async def fetch_async(host, port):
    """Non-blocking HTTP fetch. Returns parsed JSON dict or None on error."""
    gc.collect()
    try:
        data = await asyncio.wait_for(_do_get(host, port), timeout=10)
        gc.collect()
        return data
    except asyncio.TimeoutError:
        print("api: timeout connecting to", host, port)
        gc.collect()
        return None
    except Exception as e:
        print("api:", type(e).__name__, e)
        gc.collect()
        return None
