"""Fetch usage metrics from the relay server over local HTTP."""

import urequests
import gc


def fetch(server_url):
    """Fetch usage data from the relay server.

    Args:
        server_url: Base URL like "http://192.168.1.100:8265"

    Returns:
        dict with session/daily/models data, or None on error.
    """
    gc.collect()
    try:
        resp = urequests.get(server_url + "/api/usage")
        if resp.status_code != 200:
            resp.close()
            return None
        data = resp.json()
        resp.close()
        gc.collect()
        return data
    except Exception as e:
        print("api:", e)
        return None
