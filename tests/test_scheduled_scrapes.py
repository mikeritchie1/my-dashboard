from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


REPO_DIR = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_DIR))

from services import run_scheduled_scrapes


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ScheduledScrapeTests(unittest.TestCase):
    def test_fetch_controls_uses_browser_user_agent(self) -> None:
        seen_headers: dict[str, str] = {}

        def fake_urlopen(request: object, timeout: int = 0) -> FakeResponse:
            del timeout
            seen_headers.update(getattr(request, "headers", {}))
            return FakeResponse({"modules": {}})

        with patch.object(run_scheduled_scrapes, "state_url", return_value="https://example.test/state"):
            with patch.object(run_scheduled_scrapes.urllib.request, "urlopen", side_effect=fake_urlopen):
                controls = run_scheduled_scrapes.fetch_scrape_controls()

        self.assertEqual({"modules": {}}, controls)
        self.assertIn("Mozilla/5.0", seen_headers.get("User-agent", ""))

    def test_fetch_controls_failure_disables_selected_sources(self) -> None:
        error = HTTPError("https://example.test/state", 403, "Forbidden", None, None)

        with patch.object(run_scheduled_scrapes, "state_url", return_value="https://example.test/state"):
            with patch.object(run_scheduled_scrapes.urllib.request, "urlopen", side_effect=error):
                controls = run_scheduled_scrapes.fetch_scrape_controls()

        self.assertTrue(controls[run_scheduled_scrapes.CONTROLS_UNAVAILABLE_KEY])
        self.assertEqual([], run_scheduled_scrapes.selected_sources(controls, "hourly"))

    def test_disabled_schedule_skips_source(self) -> None:
        controls = {
            "version": 2,
            "modules": {
                "one-piece": {
                    "enabled": True,
                    "sources": {
                        "bigbang": {
                            "enabled": True,
                            "schedule": "disabled",
                        },
                    },
                },
            },
        }

        selected = run_scheduled_scrapes.selected_sources(controls, "hourly")

        self.assertFalse(any(item.module == "one-piece" and item.source == "bigbang" for item in selected))

    def test_marvellous_is_disabled_for_legacy_controls(self) -> None:
        controls = {
            "version": 1,
            "modules": {
                "one-piece": {
                    "enabled": True,
                    "sources": {
                        "marvellous": {
                            "enabled": True,
                            "schedule": "hourly",
                        },
                    },
                },
            },
        }

        selected = run_scheduled_scrapes.selected_sources(controls, "hourly")

        self.assertFalse(any(item.module == "one-piece" and item.source == "marvellous" for item in selected))

    def test_marvellous_can_be_reenabled_after_controls_migration(self) -> None:
        controls = {
            "version": 2,
            "modules": {
                "one-piece": {
                    "enabled": True,
                    "sources": {
                        "marvellous": {
                            "enabled": True,
                            "schedule": "hourly",
                        },
                    },
                },
            },
        }

        selected = run_scheduled_scrapes.selected_sources(controls, "hourly")

        self.assertTrue(any(item.module == "one-piece" and item.source == "marvellous" for item in selected))

    def test_scheduled_hard_option_requires_environment_opt_in(self) -> None:
        config = next(
            item
            for item in run_scheduled_scrapes.SOURCE_CONFIGS
            if item.module == "one-piece" and item.source == "products"
        )
        controls = {"modules": {"one-piece": {"options": {"hard": True}}}}

        with patch.dict(run_scheduled_scrapes.os.environ, {}, clear=True):
            command = run_scheduled_scrapes.with_options(config.command, config, controls)
        self.assertNotIn("--hard", command)

        with patch.dict(run_scheduled_scrapes.os.environ, {"DASHBOARD_ALLOW_SCHEDULED_HARD": "1"}, clear=True):
            command = run_scheduled_scrapes.with_options(config.command, config, controls)
        self.assertIn("--hard", command)


if __name__ == "__main__":
    unittest.main()
