import gzip
from unittest import TestCase
from unittest.mock import MagicMock, patch
import zlib

from services.release_radar import scrape_galileo as galileo


class GalileoFetchTests(TestCase):
    def test_decodes_compressed_and_plain_pages(self):
        html = '<li class="wcs-class"><h3 class="titledesktop">Twilight</h3><a class="wcs-btn" href="/twilight/">Info</a></li>'
        for encoding, content in (("gzip", gzip.compress(html.encode())), ("", gzip.compress(html.encode())), ("deflate", zlib.compress(html.encode())), ("", html.encode())):
            with self.subTest(encoding=encoding, compressed=content != html.encode()):
                response = MagicMock()
                response.__enter__.return_value = response
                response.read.return_value = content
                response.headers = {"Content-Encoding": encoding}
                with patch.object(galileo.urllib.request, "urlopen", return_value=response):
                    decoded = galileo.fetch_html("https://example.test")
                self.assertEqual(html, decoded)
                self.assertEqual("Twilight", galileo.parse_listing_movies(decoded)[0]["title"])

    def test_unreadable_listing_is_an_error(self):
        with patch.object(galileo, "fetch_html", return_value="<html>Maintenance</html>"):
            with self.assertRaisesRegex(RuntimeError, "no readable movie listings"):
                galileo.scrape_galileo()
