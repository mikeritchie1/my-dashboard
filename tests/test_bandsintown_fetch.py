import gzip
from pathlib import Path
import sys
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services/events"))
import scrape_bandsintown_events as bt


class BandsintownFetchTests(TestCase):
    def test_blocked_page_is_not_an_empty_success(self):
        with patch.object(bt, "fetch_html", side_effect=HTTPError(bt.SOURCE_URL, 403, "Forbidden", None, None)):
            with self.assertRaisesRegex(RuntimeError, "blocked.*403"):
                bt.collect_listing_links(bt.SOURCE_URL, 2)

    def test_unreadable_page_is_not_an_empty_success(self):
        with patch.object(bt, "fetch_html", return_value="<html>No readable content</html>"):
            with self.assertRaisesRegex(RuntimeError, "no readable event links"):
                bt.collect_listing_links(bt.SOURCE_URL, 2)

    def test_compressed_listing_decodes_before_parsing(self):
        text = '<a href="/e/123-example-at-venue">Example</a>'
        response = MagicMock()
        response.__enter__.return_value = response
        response.headers = {"Content-Encoding": "gzip"}
        response.read.return_value = gzip.compress(text.encode())
        with patch.object(bt.urllib.request, "urlopen", return_value=response):
            page = bt.fetch_html(bt.SOURCE_URL)
        self.assertEqual(1, len(bt.parse_city_links(page)))

    def test_hard_run_keeps_saved_file_when_blocked(self):
        with patch.object(bt.sys, "argv", ["scraper", "--hard"]), patch.object(bt, "scrape", side_effect=RuntimeError("blocked")), patch.object(Path, "unlink") as unlink, patch.object(bt, "sync_events_data_to_docs") as sync:
            with self.assertRaisesRegex(RuntimeError, "blocked"):
                bt.main()
            unlink.assert_not_called()
            sync.assert_not_called()
