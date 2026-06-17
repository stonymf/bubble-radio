import os
import tempfile
import unittest
from unittest import mock

import src.downloader as downloader
from src.downloader import _download_and_convert, http_requests


class FakeResponse:
    """Minimal stand-in for a requests.Response from the YouTube proxy."""

    def __init__(self, status_code, json_body=None, content=b"", content_type="application/json"):
        self.status_code = status_code
        self._json = json_body
        self.content = content
        self.headers = {"Content-Type": content_type}

    def json(self):
        if self._json is None:
            raise ValueError("response body is not JSON")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise http_requests.HTTPError(
                f"{self.status_code} Server Error: Internal Server Error for url: "
                "http://proxy/cc/download"
            )


class DownloadAndConvertProxyErrorTest(unittest.TestCase):
    def setUp(self):
        # Force the proxy path on for a YouTube URL.
        patches = [
            mock.patch.object(downloader, "YT_PROXY_URL", "http://proxy"),
            mock.patch.object(downloader, "YT_PROXY_SECRET", "secret"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.url = "https://www.youtube.com/watch?v=abc123"

    def test_proxy_500_with_json_surfaces_real_error(self):
        real_error = "ERROR: unable to download video data: HTTP Error 403: Forbidden"
        resp = FakeResponse(500, json_body={"error": real_error})
        with mock.patch.object(http_requests, "post", return_value=resp):
            with self.assertRaises(ValueError) as ctx:
                _download_and_convert(self.url, "/tmp/ignored")
        self.assertIn("403: Forbidden", str(ctx.exception))

    def test_proxy_200_audio_writes_file(self):
        audio = b"ID3\x03\x00\x00\x00fake mp3 bytes"
        resp = FakeResponse(200, content=audio, content_type="audio/mpeg")
        with tempfile.TemporaryDirectory() as tmp:
            outtmpl = os.path.join(tmp, "song")
            with mock.patch.object(http_requests, "post", return_value=resp):
                _download_and_convert(self.url, outtmpl)
            with open(f"{outtmpl}.mp3", "rb") as f:
                self.assertEqual(f.read(), audio)

    def test_proxy_500_non_json_still_raises(self):
        resp = FakeResponse(500, json_body=None, content=b"<html>oops</html>",
                            content_type="text/html")
        with mock.patch.object(http_requests, "post", return_value=resp):
            with self.assertRaises(http_requests.HTTPError):
                _download_and_convert(self.url, "/tmp/ignored")


if __name__ == "__main__":
    unittest.main()
