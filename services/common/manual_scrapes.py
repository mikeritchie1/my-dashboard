"""One-off requests from the dashboard, using the existing shared state API."""
from concurrent.futures import ThreadPoolExecutor
import json
from urllib.request import Request, urlopen


def request_key(config):
    return f"manual-scrape:{config.module}:{config.source}"


def read_request(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def write_request(url, payload):
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST",
                      headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=20) as response:
        response.read()


def pending_requests(configs, state_url):
    def read(config):
        url = state_url(request_key(config))
        if not url:
            return None
        try:
            payload = read_request(url)
            if payload.get("status") == "queued" and isinstance(payload.get("request_id"), str):
                return (f"{config.module}/{config.source}", payload)
        except Exception as error:
            print(f"Could not check manual request {config.module}/{config.source}: {error}", flush=True)
        return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(item for item in pool.map(read, configs) if item)
