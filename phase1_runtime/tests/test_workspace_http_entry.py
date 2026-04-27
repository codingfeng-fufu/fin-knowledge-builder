from __future__ import annotations

from http import HTTPStatus
import http.client
import threading
import time
import unittest

from phase1_runtime.api import create_server


class WorkspaceHttpEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = create_server(host="127.0.0.1", port=0)
        self.host, self.port = self.server.server_address
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def _request(self, path: str) -> tuple[int, str, str]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=5)
        connection.request("GET", path)
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        connection.close()
        return response.status, content_type, payload

    def test_root_path_serves_workspace(self) -> None:
        status, content_type, payload = self._request("/")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("金融规则资产专家工作台", payload)
        self.assertIn("上传文档，直接提问", payload)
