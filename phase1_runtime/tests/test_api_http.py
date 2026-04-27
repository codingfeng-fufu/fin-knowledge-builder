from __future__ import annotations

from http import HTTPStatus
import http.client
import json
import tempfile
import threading
import time
import unittest

from phase1_runtime.api import create_server


class Phase1ApiHttpTests(unittest.TestCase):
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

    def _request(self, method: str, path: str, body: str | None = None) -> tuple[int, str, str]:
        connection = http.client.HTTPConnection(self.host, self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
        content_type = response.getheader("Content-Type", "")
        connection.close()
        return response.status, content_type, payload

    def test_health_endpoint(self) -> None:
        status, _content_type, payload = self._request("GET", "/health")
        data = json.loads(payload)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["ok"])
        self.assertEqual(data["status"], "healthy")

    def test_console_page(self) -> None:
        status, content_type, payload = self._request("GET", "/console")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("Phase 1 Registry Console", payload)

    def test_prototype_page(self) -> None:
        status, content_type, payload = self._request("GET", "/prototype")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("金融规则资产平台原型", payload)

    def test_ops_page(self) -> None:
        status, content_type, payload = self._request("GET", "/ops")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("规则资产运营后台", payload)
        self.assertIn("检索后端状态", payload)

    def test_product_page(self) -> None:
        status, content_type, payload = self._request("GET", "/workspace")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("金融规则资产专家工作台", payload)
        self.assertIn("上传文档，直接提问", payload)
        self.assertIn("查看 Skill Preview", payload)

    def test_workflow_page(self) -> None:
        status, content_type, payload = self._request("GET", "/workflow")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)
        self.assertIn("系统工作流", payload)
        self.assertIn("回答与依据", payload)

    def test_post_api_phase1_product_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status, _content_type, payload = self._request(
                "POST",
                "/api/phase1",
                body=json.dumps({
                    "action": "product.solve.preview",
                    "scenario_id": "fund_nav_warning",
                    "question_text": "是否需要向投资者进行风险提示？",
                    "work_dir": tmpdir,
                }),
            )
            data = json.loads(payload)
            self.assertEqual(status, HTTPStatus.OK)
            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["decision_text"], "需要进行风险提示")

    def test_post_api_phase1_product_workspace_solve(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status, _content_type, payload = self._request(
                "POST",
                "/api/phase1",
                body=json.dumps({
                    "action": "product.workspace.solve",
                    "question_text": "是否需要发送借款人通知？",
                    "materials": [
                        {
                            "name": "notice_clause.txt",
                            "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                        }
                    ],
                    "work_dir": tmpdir,
                }),
            )
            data = json.loads(payload)
            self.assertEqual(status, HTTPStatus.OK)
            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["scenario_id"], "credit_notice")
            # With signal detection, routing depends on which hints are found
            self.assertIn(data["data"]["route_decision"], {"direct_match", "rule_composable", "needs_more_context", "exploration"})

    def test_post_api_phase1_prototype_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            status, _content_type, payload = self._request(
                "POST",
                "/api/phase1",
                body=json.dumps({"action": "prototype.flow.run", "flow_id": "credit_compose", "work_dir": tmpdir}),
            )
            data = json.loads(payload)
            self.assertEqual(status, HTTPStatus.OK)
            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["route_decision"], "rule_composable")
            self.assertEqual(data["data"]["final_decision"], "must_notify")

    def test_post_api_phase1_workflow(self) -> None:
        status, _content_type, payload = self._request(
            "POST",
            "/api/phase1",
            body=json.dumps({"action": "workflow.full", "request_id": "http_req_001"}),
        )
        data = json.loads(payload)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["ok"])
        self.assertEqual(data["request_id"], "http_req_001")
        self.assertEqual(data["data"]["workflow_status"], "completed")

    def test_post_api_phase1_registry_list(self) -> None:
        status, _content_type, payload = self._request(
            "POST",
            "/api/phase1",
            body=json.dumps({"action": "registry.dataset.list", "db_path": "phase1_runtime/state/registry.db"}),
        )
        data = json.loads(payload)
        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(data["ok"])
        self.assertIn("dataset_count", data["data"])

    def test_post_api_phase1_factory_case_ingest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = f"{tmpdir}/registry.db"
            status, _content_type, payload = self._request(
                "POST",
                "/api/phase1",
                body=json.dumps(
                    {
                        "action": "factory.case.ingest",
                        "dataset_dir": "phase1_runtime/sim_data/demo_set_001",
                        "db_path": db_path,
                        "source": "http_test",
                    }
                ),
            )
            data = json.loads(payload)
            self.assertEqual(status, HTTPStatus.OK)
            self.assertTrue(data["ok"])
            self.assertEqual(data["data"]["dataset_id"], "demo_set_001")

            list_status, _content_type, list_payload = self._request(
                "POST",
                "/api/phase1",
                body=json.dumps({"action": "factory.case.list", "db_path": db_path}),
            )
            list_data = json.loads(list_payload)
            self.assertEqual(list_status, HTTPStatus.OK)
            self.assertEqual(list_data["data"]["case_count"], 1)

    def test_post_api_phase1_invalid_json(self) -> None:
        status, _content_type, payload = self._request("POST", "/api/phase1", body="{bad json")
        data = json.loads(payload)
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "bad_request")

    def test_post_api_phase1_unsupported_action(self) -> None:
        status, _content_type, payload = self._request(
            "POST",
            "/api/phase1",
            body=json.dumps({"action": "dataset.unknown"}),
        )
        data = json.loads(payload)
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "unsupported_action")


if __name__ == "__main__":
    unittest.main()
