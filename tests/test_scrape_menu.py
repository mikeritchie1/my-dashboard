import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch

from services import run_scheduled_scrapes as runner
from services.common import scrape_metadata as metadata
from services.common import scrape_notifications as notifications
from services.common import scrape_summary as summary
from services.common import manual_scrapes
from services.common.scrape_options import source_option


class ScrapeMenuTests(TestCase):
    def setUp(self):
        self.config = next(c for c in runner.SOURCE_CONFIGS if c.source == "knightly")
        self.before = {"a": {"title": "Old", "price": 50}, "b": {"title": "Changed", "price": 80}}
        self.after = {"b": {"title": "Changed", "price": 90}, "c": {"title": "New", "price": 70}}
        self.controls = {"version": 2, "modules": {"one-piece": {"sources": {"knightly": {
            "enabled": True, "schedule": "weekly", "email": {"added": True, "removed": True, "updated": True}
        }}, "options": {"max_price": 100}}}}

    def test_source_interval_override_and_interval_run_switch(self):
        self.assertIn(self.config, runner.selected_sources(self.controls, "weekly"))
        self.assertNotIn(self.config, runner.selected_sources(self.controls, "hourly"))
        self.controls["interval_enabled"] = {"weekly": False}
        self.assertEqual([], runner.selected_sources(self.controls, "weekly"))

    def test_module_disable_blocks_sources(self):
        self.controls["modules"]["one-piece"]["enabled"] = False
        self.assertNotIn(self.config, runner.selected_sources(self.controls, "weekly"))

    def test_email_gates_and_price(self):
        sections = notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after)
        self.assertEqual(3, len(sections))
        self.controls["email_enabled"] = False
        self.assertEqual([], notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after))
        self.controls["email_enabled"] = True
        self.controls["interval_email_enabled"] = {"weekly": False}
        self.assertEqual([], notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after))
        self.controls["interval_email_enabled"]["weekly"] = True
        self.controls["modules"]["one-piece"]["options"]["max_price"] = 60
        self.assertEqual(1, len(notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after)))

    def test_store_rows_exclude_other_stores(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / self.config.outputs[0]
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"listings": [
                {"store": "Knightly Gaming", "url": "a", "title": "A"},
                {"store": "Big Bang Shop", "url": "b", "title": "B"},
            ]}))
            self.assertEqual(1, len(notifications.read_source_rows(root, self.config)))

    def test_summary_accumulates_runs_and_deduplicates_titles_by_item(self):
        pending = {"window_started_at": "today", "sources": {}}
        summary.collect(pending, self.config, self.before, self.after)
        summary.collect(pending, self.config, self.before, self.after)
        entry = pending["sources"]["one-piece/knightly"]
        self.assertEqual(2, entry["runs"])
        self.assertEqual(["New"], list(entry["added"].values()))
        self.assertEqual(["Old"], list(entry["removed"].values()))
        self.assertIn("Changed", summary.summary_body(pending))

    def test_summary_delivery_and_failure_preserve_correct_window(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "summary.json"
            pending = summary.load_summary(path)
            summary.collect(pending, self.config, self.before, self.after)
            summary.save_summary(path, pending)
            with patch.object(summary, "send_email", side_effect=RuntimeError("SMTP down")):
                with self.assertRaises(RuntimeError):
                    summary.send_if_due(path, pending, {}, "daily")
            self.assertTrue(summary.load_summary(path)["sources"])
            with patch.object(summary, "send_email") as send:
                self.assertFalse(summary.send_if_due(path, pending, {}, "hourly"))
                self.assertFalse(summary.send_if_due(path, pending, {"email_enabled": False}, "daily"))
                send.assert_not_called()
                self.assertTrue(summary.send_if_due(path, pending, {}, "daily"))
                send.assert_called_once()
            self.assertEqual({}, summary.load_summary(path)["sources"])

    def test_history_retains_three_and_survives_new_metadata_record(self):
        with TemporaryDirectory() as directory, patch.object(metadata, "METADATA_PATH", Path(directory) / "metadata.json"):
            for count in range(5):
                metadata.record_scrape_outputs([], module="one-piece", source="knightly", duration_seconds=10, command=[])
                metadata.record_source_history("one-piece", "knightly", {}, {str(n): {} for n in range(count)})
            history = metadata.read_metadata()["sources"]["one-piece/knightly"]["history"]
            self.assertEqual([2, 3, 4], [h["item_count"] for h in history])
            self.assertEqual([2, 3, 4], [h["added"] for h in history])

    def test_store_command_does_not_scrape_products(self):
        self.assertIn("--skip-products", runner.with_options(self.config.command, self.config, {}))

    def test_source_option_inheritance_blank_and_zero(self):
        controls = {"modules": {"events": {"options": {"limit": 30}, "sources": {"quicket": {"options": {}}}}}}
        options = controls["modules"]["events"]["sources"]["quicket"]["options"]
        for value in (None, ""):
            options["limit"] = value
            self.assertEqual(30, source_option(controls, "events", "quicket", "limit"))
        options["limit"] = 0
        self.assertEqual(0, source_option(controls, "events", "quicket", "limit"))
        options["limit"] = 7
        config = next(c for c in runner.SOURCE_CONFIGS if c.module == "events" and c.source == "quicket")
        command = runner.with_options(config.command, config, controls)
        self.assertEqual("7", command[command.index("--limit") + 1])

    def test_source_price_override_and_module_fallback(self):
        options = self.controls["modules"]["one-piece"]["sources"]["knightly"].setdefault("options", {})
        options["max_price"] = 60
        self.assertEqual(1, len(notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after)))
        options["max_price"] = ""
        self.assertEqual(3, len(notifications.change_sections(self.config, self.controls, "weekly", self.before, self.after)))

    def test_manual_queue_accepts_only_queued_requests(self):
        with patch.object(manual_scrapes, "read_request", return_value={"status": "queued", "request_id": "test"}):
            pending = manual_scrapes.pending_requests([self.config], lambda key: "https://example.test/" + key)
        self.assertIn("one-piece/knightly", pending)
        with patch.object(manual_scrapes, "read_request", return_value={"status": "running", "request_id": "test"}):
            self.assertEqual({}, manual_scrapes.pending_requests([self.config], lambda key: "https://example.test/" + key))

    def test_manual_run_bypasses_automatic_switches_and_reports_completion(self):
        controls = {"interval_enabled": {"ten-minute": False}, "email_enabled": False}
        pending = {"one-piece/knightly": {"status": "queued", "request_id": "test"}}
        with (
            patch.object(runner.sys, "argv", ["scheduler", "--interval", "ten-minute"]),
            patch.object(runner, "fetch_scrape_controls", return_value=controls),
            patch.object(runner.manual_scrapes, "pending_requests", return_value=pending),
            patch.object(runner.manual_scrapes, "write_request") as write,
            patch.object(runner, "state_url", return_value="https://example.test/state"),
            patch.object(runner, "load_summary", return_value={"window_started_at": "today", "sources": {}}),
            patch.object(runner, "save_summary"),
            patch.object(runner, "read_source_rows", side_effect=[self.before, self.after]),
            patch.object(runner, "run_command", return_value={"returncode": 0}) as run,
            patch.object(runner, "record_source_history"),
            patch.object(runner, "read_metadata", return_value={"sources": {"one-piece/knightly": {"item_count": 2}}}),
            patch.object(runner, "send_sections"),
            patch.object(runner, "send_if_due"),
        ):
            self.assertEqual(0, runner.main())
        run.assert_called_once_with(self.config, controls)
        self.assertEqual("running", write.call_args_list[0].args[1]["status"])
        self.assertEqual("finished", write.call_args_list[1].args[1]["status"])
        self.assertEqual(2, write.call_args_list[1].args[1]["stats"]["item_count"])


if __name__ == "__main__":
    main()
