"""Create a local owner password, optionally configure and deploy online login."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.common.secrets import local_secret


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deploy", action="store_true")
    args = parser.parse_args()
    password = local_secret("DASHBOARD_PASSWORD")
    if not password:
        password = secrets.token_urlsafe(24)
        path = ROOT / "secrets.env"
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        found = False
        for index, line in enumerate(lines):
            if line.split("=", 1)[0].strip() == "DASHBOARD_PASSWORD":
                lines[index] = "DASHBOARD_PASSWORD=" + password
                found = True
        if not found:
            lines.extend(["", "# Owner dashboard visibility login", "DASHBOARD_PASSWORD=" + password])
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Owner password is stored in secrets.env as DASHBOARD_PASSWORD.", flush=True)
    if not args.deploy:
        return
    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json", dir=cache, delete=False) as stream:
            json.dump({"DASHBOARD_PASSWORD": password}, stream)
            filename = Path(stream.name)
        result = subprocess.run(["npx.cmd" if os.name == "nt" else "npx", "--yes", "wrangler", "deploy",
                                 "--secrets-file", str(filename)], cwd=ROOT / "cloudflare-state-worker")
        if result.returncode:
            raise SystemExit(result.returncode)
    finally:
        if filename:
            filename.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
