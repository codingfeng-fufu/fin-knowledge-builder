from __future__ import annotations

import tempfile
import unittest

from phase1_runtime.api import handle_request


class WorkspaceContractTests(unittest.TestCase):
    def test_workspace_contract_action(self) -> None:
        response = handle_request({"action": "product.workspace.contract"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["entry_path"], "/workspace")
        self.assertEqual(response["data"]["parser_status"], "document_parser_mvp_connected")
        self.assertIn("document_parser_contract", response["data"])

    def test_workspace_solve_includes_parser_previews(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            response = handle_request(
                {
                    "action": "product.workspace.solve",
                    "question_text": "是否需要发送借款人通知？",
                    "materials": [
                        {
                            "name": "notice_clause.txt",
                            "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                        }
                    ],
                    "work_dir": tmpdir,
                }
            )
            self.assertTrue(response["ok"])
            data = response["data"]
            self.assertEqual(data["input_mode"], "expert_workspace")
            self.assertEqual(data["workspace_contract"]["entry_path"], "/workspace")
            self.assertEqual(data["document_parser_contract"]["status"], "document_parser_mvp_connected")
            self.assertEqual(data["parser_bridge_status"], "runtime_connected")
            self.assertEqual(data["document_packet_preview"]["document_count"], 1)
            self.assertEqual(data["question_packet_preview"]["question_type"], "decision_query")
            self.assertGreaterEqual(len(data["fact_sheet"]), 1)
