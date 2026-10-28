from functools import partial
from http.server import ThreadingHTTPServer
import json
import threading
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import serve_dashboard as local


class LocalScrapeTests(TestCase):
    def test_module_runs_enabled_sources_in_order(self):
        jobs = local.ScrapeJobs()
        controls = {"modules": {"one-piece": {"sources": {
            c.source: {"enabled": c.source in {"knightly", "products"}} for c in local.runner.SOURCE_CONFIGS if c.module == "one-piece"
        }}}}
        seen = []
        with patch.object(jobs, "run", side_effect=lambda config, options: seen.append(config.source)):
            jobs.submit("one-piece", "*", controls)
            jobs.executor.shutdown(wait=True)
        self.assertEqual(["knightly", "products"], seen)

    def test_individual_manual_run_overrides_disabled_schedule(self):
        jobs = local.ScrapeJobs()
        with patch.object(jobs, "run") as run:
            jobs.submit("one-piece", "knightly", {"modules": {"one-piece": {"enabled": False}}})
            jobs.executor.shutdown(wait=True)
        self.assertEqual("knightly", run.call_args.args[0].source)

    def test_duplicate_and_unknown_commands(self):
        jobs = local.ScrapeJobs()
        with patch.object(jobs.executor, "submit") as submit:
            jobs.submit("one-piece", "knightly", {})
            jobs.submit("one-piece", "knightly", {})
            self.assertEqual(1, submit.call_count)
            with self.assertRaises(ValueError):
                jobs.submit("shell", "arbitrary-command", {})
        jobs.executor.shutdown(wait=True)

    def test_success_reports_counts_and_history(self):
        jobs = local.ScrapeJobs()
        with (
            patch.object(local.runner, "read_source_rows", side_effect=[{}, {"card": {"title": "Card"}}]),
            patch.object(local.runner, "run_command", return_value={"returncode": 0}),
            patch.object(local.runner, "record_source_history") as record,
            patch.object(local, "load_summary", return_value={"window_started_at": "today", "sources": {}}),
            patch.object(local, "save_summary"),
            patch.object(local.runner, "read_metadata", return_value={"sources": {"one-piece/knightly": {"item_count": 1, "duration_seconds": 12}}}),
        ):
            jobs.submit("one-piece", "knightly", {})
            jobs.executor.shutdown(wait=True)
        result = jobs.snapshot()["one-piece/knightly"]
        self.assertEqual("finished", result["status"])
        self.assertEqual(1, result["stats"]["item_count"])
        record.assert_called_once()

    def test_failure_has_retry_status(self):
        jobs = local.ScrapeJobs()
        with patch.object(local.runner, "read_source_rows", return_value={}), patch.object(local.runner, "run_command", side_effect=RuntimeError("offline")):
            jobs.submit("one-piece", "knightly", {})
            jobs.executor.shutdown(wait=True)
        result = jobs.snapshot()["one-piece/knightly"]
        self.assertEqual("error", result["status"])
        self.assertEqual("offline", result["error"])


class LocalHttpTests(TestCase):
    def setUp(self):
        self.secret_patch = patch.object(local, "secret", return_value="configured")
        self.secret_patch.start()
        self.addCleanup(self.secret_patch.stop)
        self.jobs = local.ScrapeJobs()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(local.DashboardHandler, jobs=self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.jobs.executor.shutdown(wait=True)

    def test_health_and_dashboard(self):
        with urlopen(self.base + "/api/scrapes") as response:
            self.assertTrue(json.load(response)["local_scrapes"])
        with urlopen(self.base + "/docs/") as response:
            self.assertIn(b"<html", response.read().lower())

    def test_files_outside_docs_are_not_served(self):
        for path in ("/secrets.env", "/.git/config", "/docs/../secrets.env"):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path)
            self.assertEqual(404, error.exception.code)

    def test_cross_origin_execution_is_rejected(self):
        request = Request(self.base + "/api/scrapes", data=b"{}", headers={"Content-Type": "application/json", "Origin": "https://other.example"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(403, error.exception.code)

    def test_unknown_source_is_rejected(self):
        request = Request(self.base + "/api/scrapes", data=b'{"module":"shell","source":"run"}', headers={"Content-Type": "application/json"})
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(400, error.exception.code)

    def test_newsletter_sends_current_preview(self):
        summary = {"window_started_at": "today", "sources": {"test": {"label": "Test"}}}
        payload = {"controls": {"email_enabled": True, "summary_interval": "daily"}, "summary": summary}
        request = Request(self.base + "/api/newsletter/send", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with patch.object(local, "load_summary", return_value=summary), patch.object(local, "send_if_due", return_value=True) as send:
            with urlopen(request) as response:
                self.assertTrue(json.load(response)["sent"])
            send.assert_called_once()
            self.assertFalse(send.call_args.kwargs["clear_after_send"])

    def test_newsletter_rejects_stale_preview(self):
        request = Request(self.base + "/api/newsletter/send", data=b'{"controls":{"email_enabled":true},"summary":{}}', headers={"Content-Type": "application/json"})
        with patch.object(local, "load_summary", return_value={"sources": {"test": {}}}), patch.object(local, "send_if_due") as send:
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(409, error.exception.code)
            send.assert_not_called()

    def test_newsletter_delivery_failure_does_not_claim_success(self):
        summary = {"sources": {"test": {}}}
        payload = {"controls": {"email_enabled": True}, "summary": summary}
        request = Request(self.base + "/api/newsletter/send", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with patch.object(local, "load_summary", return_value=summary), patch.object(local, "send_if_due", side_effect=RuntimeError("SMTP offline")):
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertEqual(502, error.exception.code)

    def test_newsletter_lists_missing_settings_without_sending(self):
        summary = {"sources": {"test": {}}}
        payload = {"controls": {"email_enabled": True}, "summary": summary}
        request = Request(self.base + "/api/newsletter/send", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with patch.object(local, "load_summary", return_value=summary), patch.object(local, "secret", return_value=""), patch.object(local, "send_if_due") as send:
            with self.assertRaises(HTTPError) as error:
                urlopen(request)
            self.assertIn("SMTP_PASSWORD", json.load(error.exception)["error"])
            send.assert_not_called()
