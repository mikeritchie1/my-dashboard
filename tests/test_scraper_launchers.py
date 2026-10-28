import os
from pathlib import Path
import subprocess
import sys
from unittest import TestCase


class ScraperLauncherTests(TestCase):
    def test_wrappers_launch_directly_without_pythonpath(self):
        root = Path(__file__).resolve().parents[1]
        env = {key: value for key, value in os.environ.items() if key.upper() != "PYTHONPATH"}
        for script in ("scrape_release_radar.py", "scrape_events.py", "scrape_media.py", "scrape_one_piece.py"):
            with self.subTest(script=script):
                result = subprocess.run([sys.executable, str(root / "services" / script), "--help"],
                                        cwd=root, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("--source", result.stdout)
