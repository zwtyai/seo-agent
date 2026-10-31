"""来源 URL 存活检查。不打真网，全部 mock。"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from core.urlcheck import host_blocked, probe_source_url


class UrlCheckTest(unittest.TestCase):
    def test_host_blocked_grounding_and_baidu(self):
        self.assertTrue(
            host_blocked(
                "https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc"
            )
        )
        self.assertTrue(host_blocked("https://baijiahao.baidu.com/s?id=1"))
        self.assertIsNone(host_blocked("https://www.britannica.com/plant/banana"))

    def test_probe_requires_http_200(self):
        response = MagicMock()
        response.geturl.return_value = "https://www.britannica.com/plant/banana"
        response.status = 200
        response.getcode.return_value = 200
        response.read.return_value = b"ok"
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch("core.urlcheck.urlopen", return_value=response):
            ok, reason = probe_source_url("https://www.britannica.com/plant/banana")
        self.assertTrue(ok, reason)
        self.assertIn("200", reason)

    def test_probe_rejects_http_error(self):
        err = HTTPError(
            url="https://example.com/gone",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=None,
        )
        with patch("core.urlcheck.urlopen", side_effect=err):
            ok, reason = probe_source_url("https://example.com/gone")
        self.assertFalse(ok)
        self.assertIn("404", reason)


if __name__ == "__main__":
    unittest.main()
