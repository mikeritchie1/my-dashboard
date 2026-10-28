"""Serve the dashboard and execute allowlisted scrapers on this computer."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from uuid import uuid4

from services import run_scheduled_scrapes as runner
from services.common.scrape_summary import load_summary, save_summary, collect

ROOT = Path(__file__).resolve().parent


class ScrapeJobs:
    def __init__(self):
        self.jobs = {}
        self.lock = threading.RLock()
        # Scrapers share output files; serialize all commands, including module runs.
        self.executor = ThreadPoolExecutor(max_workers=1)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.jobs))

    def submit(self, module, source, controls):
        configs = [c for c in runner.SOURCE_CONFIGS if c.module == module and (source == "*" or c.source == source)]
        if source == "*":
            configs = [c for c in configs if runner.source_state(controls, c).get("enabled", c.default_enabled)
                       and runner.source_state(controls, c).get("schedule") != "disabled"]
        if not configs:
            raise ValueError("No matching enabled scrapers")
        with self.lock:
            for config in configs:
                key = f"{config.module}/{config.source}"
                if self.jobs.get(key, {}).get("status") in {"queued", "running"}:
                    continue
                self.jobs[key] = {"request_id": str(uuid4()), "status": "queued"}
                self.executor.submit(self.run, config, controls)
        return self.snapshot()

    def run(self, config, controls):
        key = f"{config.module}/{config.source}"
        with self.lock:
            self.jobs[key]["status"] = "running"
        try:
            before = runner.read_source_rows(ROOT, config)
            result = runner.run_command(config, controls)
            if result["returncode"]:
                raise RuntimeError(f"Scraper exited with code {result['returncode']}")
            after = runner.read_source_rows(ROOT, config)
            runner.record_source_history(config.module, config.source, before, after)
            path = ROOT / "docs/data/scrape_summary.json"
            summary = load_summary(path)
            collect(summary, config, before, after)
            save_summary(path, summary)
            stats = runner.read_metadata()["sources"][key]
            with self.lock:
                self.jobs[key].update(status="finished", stats=stats)
        except Exception as error:
            with self.lock:
                self.jobs[key].update(status="error", error=str(error),
                                      stats=runner.read_metadata().get("sources", {}).get(key, {}))


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, jobs, **kwargs):
        self.jobs = jobs
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def local_request(self):
        host = urlsplit("http://" + self.headers.get("Host", "")).hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return False
        origin = self.headers.get("Origin")
        return not origin or origin == "http://" + self.headers.get("Host", "")

    def json_response(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        if not self.local_request():
            return self.json_response({"error": "Local requests only"}, 403)
        path = urlsplit(self.path).path
        if path == "/api/scrapes":
            return self.json_response({"local_scrapes": True, "jobs": self.jobs.snapshot()})
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/docs/")
            self.end_headers()
            return
        resolved = Path(self.translate_path(self.path)).resolve()
        if not resolved.is_relative_to((ROOT / "docs").resolve()):
            return self.json_response({"error": "Not found"}, 404)
        if self.command == "HEAD":
            super().do_HEAD()
        else:
            super().do_GET()

    def do_HEAD(self):
        # Apply the same path restrictions as GET, including for secrets outside docs.
        self.do_GET()

    def do_POST(self):
        if not self.local_request():
            return self.json_response({"error": "Local requests only"}, 403)
        if urlsplit(self.path).path != "/api/scrapes":
            return self.json_response({"error": "Not found"}, 404)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.json_response({"error": "JSON required"}, 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 262144:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            controls = payload.get("controls", {})
            if not isinstance(controls, dict):
                raise ValueError("Invalid scrape options")
            jobs = self.jobs.submit(payload.get("module"), payload.get("source"), controls)
            self.json_response({"jobs": jobs}, 202)
        except (ValueError, TypeError, AttributeError) as error:
            self.json_response({"error": str(error)}, 400)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int, nargs="?", default=8080)
    args = parser.parse_args()
    jobs = ScrapeJobs()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(DashboardHandler, jobs=jobs))
    print(f"Dashboard: http://localhost:{args.port}/docs/ (local Run buttons enabled)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.executor.shutdown(wait=True)


if __name__ == "__main__":
    main()
