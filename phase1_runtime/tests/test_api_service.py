from __future__ import annotations

from base64 import b64encode
from io import BytesIO
import json
from pathlib import Path
import zipfile
import shutil
import tempfile
import time
import unittest

from phase1_runtime.api import handle_request
from phase1_runtime.tests.mock_kimi import CREDIT_NOTICE_MOCK_VALUES, FUND_NAV_MOCK_VALUES, MockKimiExtractor


DEMO_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
CREDIT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_credit_001")


def _make_docx_bytes(paragraphs: list[str]) -> bytes:
    document_xml = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>',
    ]
    for paragraph in paragraphs:
        document_xml.append(f'<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>')
    document_xml.append('</w:body></w:document>')
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
        archive.writestr('word/document.xml', ''.join(document_xml))
    return buf.getvalue()



class Phase1ApiServiceTests(unittest.TestCase):
    def test_handle_request_full_workflow(self) -> None:
        response = handle_request(
            {
                "action": "workflow.full",
                "dataset_dir": str(DEMO_DATASET_DIR),
                "request_id": "req_full_001",
            }
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["action"], "workflow.full")
        self.assertEqual(response["request_id"], "req_full_001")
        self.assertEqual(response["data"]["workflow_status"], "completed")

    def test_handle_request_prototype_flow_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            response = handle_request(
                {
                    "action": "prototype.flow.run",
                    "flow_id": "fund_compose",
                    "work_dir": tmpdir,
                    "db_path": db_path,
                }
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["route_decision"], "rule_composable")
            self.assertEqual(response["data"]["composition_pattern"], "derive_then_decide")

    def test_handle_request_product_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            scenarios = handle_request({"action": "product.scenario.list"})
            self.assertTrue(scenarios["ok"])
            self.assertEqual(scenarios["data"]["default_scenario_id"], "fund_nav_warning")

            response = handle_request(
                {
                    "action": "product.solve.preview",
                    "scenario_id": "credit_notice",
                    "question_text": "是否需要发送借款人通知？",
                    "work_dir": tmpdir,
                }
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["decision_text"], "建议发送借款人通知")
            self.assertEqual(response["data"]["route_decision"], "rule_composable")

    def test_handle_request_demo_workspace_case_actions(self) -> None:
        list_response = handle_request({"action": "demo.workspace_case.list"})
        self.assertTrue(list_response["ok"])
        self.assertGreaterEqual(list_response["data"]["case_count"], 1)
        self.assertEqual(list_response["data"]["default_case_ref"], "workspace/fund_docx_direct_warn")

        get_response = handle_request(
            {
                "action": "demo.workspace_case.get",
                "case_ref": "workspace/fund_docx_direct_warn",
            }
        )
        self.assertTrue(get_response["ok"])
        self.assertEqual(get_response["data"]["scenario_id"], "fund_nav_warning")
        self.assertEqual(get_response["data"]["materials"][0]["name"], "fund_clause.docx")
        self.assertEqual(len(get_response["data"]["related_questions"]), 0)

    def test_handle_request_embedding_backend_status(self) -> None:
        response = handle_request({"action": "retrieval.embedding_backend.status"})
        self.assertTrue(response["ok"])
        self.assertIn("active_backend", response["data"])
        self.assertIn("available_backends", response["data"])
        self.assertIn("backend_id", response["data"]["active_backend"])

    def test_handle_request_factory_rule_graph_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "registry.db")
            response = handle_request(
                {
                    "action": "factory.rule_graph.view",
                    "db_path": db_path,
                }
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["action"], "factory.rule_graph.view")
            self.assertGreaterEqual(response["data"]["community_count"], 1)
            self.assertGreaterEqual(response["data"]["root_community_count"], 1)
            self.assertGreaterEqual(response["data"]["rag_passage_count"], 1)
            self.assertTrue(response["data"]["roots"])
            self.assertTrue(Path(response["data"]["artifact_root"]).exists())
            self.assertEqual(response["data"]["output_dir"], str((Path(tmpdir) / "rule_graph").resolve()))

    def test_handle_request_product_workspace_solve_binary_docx(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            response = handle_request(
                {
                    "action": "product.workspace.solve",
                    "question_text": "某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                    "materials": [
                        {
                            "name": "fund_clause.docx",
                            "content_base64": b64encode(_make_docx_bytes([
                                "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。",
                                "最新单位净值为0.72。",
                            ])).decode("ascii"),
                        }
                    ],
                    "work_dir": tmpdir,
                },
                kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["scenario_id"], "fund_nav_warning")
            self.assertEqual(response["data"]["decision_text"], "需要进行风险提示")
            self.assertEqual(response["data"]["parser_bridge_status"], "runtime_connected")
            self.assertEqual(response["data"]["orchestration_view"]["planner"]["planner_mode"], "direct_rule_planner")
            self.assertIn("runtime_skill_artifact", response["data"])
            self.assertTrue(response["data"]["runtime_skill_artifact"]["files"])
            self.assertNotIn("runtime_skill_artifact", response["data"]["asset_pipeline"]["workspace_run"]["payload"])
            self.assertIn("retrieval_diagnostics", response["data"]["asset_pipeline"]["workspace_run"]["payload"])

    def test_handle_request_product_workspace_solve(self) -> None:
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
                },
                kimi_client=MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES),
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["scenario_id"], "credit_notice")
            self.assertIn(response["data"]["route_decision"], {"direct_match", "rule_composable", "needs_more_context"})
            self.assertEqual(response["data"]["input_mode"], "expert_workspace")
            self.assertEqual(response["data"]["workspace_contract"]["entry_path"], "/workspace")
            self.assertEqual(response["data"]["asset_pipeline"]["auto_status"], "recorded_only")
            self.assertIn("retrieval_diagnostics", response["data"]["asset_pipeline"]["workspace_run"]["payload"])

    def test_handle_request_super_agent_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace_root = root / "workspace"
            skill_root = root / "skill"
            workspace_root.mkdir()
            skill_root.mkdir()
            (workspace_root / "facts.txt").write_text("净值0.72，阈值0.80，需要提示风险。", encoding="utf-8")
            (skill_root / "SKILL.md").write_text(
                "---\nname: fund-nav-super\ndescription: use tools and answer\n---\n\n# Skill\n",
                encoding="utf-8",
            )

            calls: list[dict[str, object]] = []

            def transport(payload: dict[str, object]) -> dict[str, object]:
                calls.append(payload)
                if len(calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "read_file",
                                                "arguments": '{"path":"facts.txt"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "最终回答：需要进行风险提示。"
                            }
                        }
                    ]
                }

            response = handle_request(
                {
                    "action": "super_agent.run",
                    "payload": {
                        "query": "是否需要进行风险提示？",
                        "skill_root": str(skill_root),
                        "workspace_root": str(workspace_root),
                        "task_context": {"scenario_id": "fund_nav_warning"},
                        "max_turns": 4,
                    },
                },
                kimi_client=transport,
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["action"], "super_agent.run")
            self.assertEqual(response["data"]["tool_call_count"], 1)
            self.assertIn("需要进行风险提示", response["data"]["final_text"])
            self.assertIn("agent_trace", response["data"])

    def test_workspace_skill_handoff_can_feed_super_agent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            solve_response = handle_request(
                {
                    "action": "product.workspace.solve",
                    "question_text": "某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                    "materials": [
                        {
                            "name": "fund_clause.txt",
                            "content": "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。最新单位净值为0.72。",
                        }
                    ],
                    "work_dir": tmpdir,
                },
                kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
            )
            self.assertTrue(solve_response["ok"])
            handoff = solve_response["data"]["super_agent_handoff"]
            self.assertIsNotNone(handoff)
            self.assertIn("context_packet", handoff["payload"])
            relative_skill_md = str(
                Path(handoff["payload"]["skill_root"]).resolve()
                .relative_to(Path(handoff["payload"]["workspace_root"]).resolve())
                / "SKILL.md"
            )

            calls: list[dict[str, object]] = []

            def transport(payload: dict[str, object]) -> dict[str, object]:
                calls.append(payload)
                if len(calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "read_file",
                                                "arguments": json.dumps(
                                                    {"path": relative_skill_md, "head": 20},
                                                    ensure_ascii=False,
                                                ),
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                return {
                    "choices": [
                        {
                            "message": {
                                "content": "最终回答：根据运行期技能与材料，当前需要进行风险提示。"
                            }
                        }
                    ]
                }

            super_response = handle_request(handoff, kimi_client=transport)
            self.assertTrue(super_response["ok"])
            self.assertEqual(super_response["action"], "super_agent.run")
            self.assertIn("需要进行风险提示", super_response["data"]["final_text"])

    def test_handle_request_workspace_run_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            solve_response = handle_request(
                {
                    "action": "product.workspace.solve",
                    "question_text": "请给出处理意见。",
                    "scenario_id": "fund_nav_warning",
                    "materials": [],
                    "work_dir": tmpdir,
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(solve_response["ok"])
            workspace_run_id = solve_response["data"]["asset_pipeline"]["workspace_run"]["workspace_run_id"]
            self.assertEqual(solve_response["data"]["asset_pipeline"]["auto_status"], "draft_promoted")

            list_response = handle_request({"action": "factory.workspace_run.list", "db_path": str(db_path)})
            self.assertTrue(list_response["ok"])
            self.assertEqual(list_response["data"]["workspace_run_count"], 1)

            get_response = handle_request({"action": "factory.workspace_run.get", "db_path": str(db_path), "workspace_run_id": workspace_run_id})
            self.assertTrue(get_response["ok"])
            self.assertEqual(get_response["data"]["workspace_run_id"], workspace_run_id)
            self.assertEqual(get_response["data"]["payload"]["auto_status"], "draft_promoted")
            self.assertIn("embedding_backend", get_response["data"]["payload"])
            self.assertIn("task_context", get_response["data"]["payload"])
            self.assertIn("rule_bindings", get_response["data"]["payload"])
            self.assertIn("runtime_skill_spec_preview", get_response["data"]["payload"])

    def test_handle_request_dataset_summary(self) -> None:
        response = handle_request(
            {
                "action": "dataset.summary",
                "dataset_dir": str(DEMO_DATASET_DIR),
            }
        )
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["dataset_id"], "demo_set_001")
        self.assertEqual(response["data"]["final_decision"], "must_warn")

    def test_handle_request_registry_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            register_response = handle_request(
                {
                    "action": "registry.dataset.register",
                    "dataset_dir": str(CREDIT_DATASET_DIR),
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(register_response["ok"])
            self.assertEqual(register_response["data"]["dataset_id"], "demo_set_credit_001")

            list_response = handle_request(
                {
                    "action": "registry.dataset.list",
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(list_response["ok"])
            self.assertEqual(list_response["data"]["dataset_count"], 1)

            run_response = handle_request(
                {
                    "action": "registry.workflow.run",
                    "dataset_id": "demo_set_credit_001",
                    "db_path": str(db_path),
                    "request_id": "api_reg_run_001",
                }
            )
            self.assertTrue(run_response["ok"])
            self.assertEqual(run_response["data"]["status"], "queued")
            run_id = run_response["data"]["run_id"]

            deadline = time.time() + 60
            get_run_response = None
            while time.time() < deadline:
                get_run_response = handle_request(
                    {
                        "action": "registry.workflow.get",
                        "run_id": run_id,
                        "db_path": str(db_path),
                    }
                )
                if get_run_response["data"]["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)

            self.assertIsNotNone(get_run_response)
            self.assertTrue(get_run_response["ok"])
            self.assertEqual(get_run_response["data"]["dataset_id"], "demo_set_credit_001")
            self.assertEqual(get_run_response["data"]["status"], "completed")

    def test_handle_request_factory_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            def call(action: str, **payload: str) -> dict[str, object]:
                return handle_request({"action": action, "db_path": str(db_path), **payload})

            ingest_response = call(
                "factory.case.ingest",
                dataset_dir=str(DEMO_DATASET_DIR),
                source="api_test",
                request_id="factory_ingest_001",
            )
            self.assertTrue(ingest_response["ok"])
            case_id = ingest_response["data"]["case_id"]

            case_list_response = call("factory.case.list")
            self.assertTrue(case_list_response["ok"])
            self.assertEqual(case_list_response["data"]["case_count"], 1)

            case_get_response = call("factory.case.get", case_id=case_id)
            self.assertTrue(case_get_response["ok"])
            self.assertEqual(case_get_response["data"]["source"], "api_test")

            draft_generate_response = call("factory.draft.generate", case_id=case_id)
            self.assertTrue(draft_generate_response["ok"])
            draft_id = draft_generate_response["data"]["draft_id"]

            draft_list_response = call("factory.draft.list")
            self.assertEqual(draft_list_response["data"]["draft_count"], 1)

            draft_get_response = call("factory.draft.get", draft_id=draft_id)
            self.assertEqual(draft_get_response["data"]["case_id"], case_id)

            review_create_response = call("factory.review.create", draft_id=draft_id, assignee="api_reviewer")
            self.assertTrue(review_create_response["ok"])
            review_task_id = review_create_response["data"]["review_task_id"]

            review_list_response = call("factory.review.list")
            self.assertEqual(review_list_response["data"]["review_count"], 1)

            review_get_response = call("factory.review.get", review_task_id=review_task_id)
            self.assertEqual(review_get_response["data"]["assignee"], "api_reviewer")

            approve_response = call(
                "factory.review.approve",
                review_task_id=review_task_id,
                note="approved by api",
            )
            self.assertTrue(approve_response["ok"])
            rule_version_id = approve_response["data"]["rule_version"]["rule_version_id"]

            version_list_response = call("factory.rule_version.list")
            self.assertEqual(version_list_response["data"]["rule_version_count"], 1)

            version_get_response = call("factory.rule_version.get", rule_version_id=rule_version_id)
            self.assertEqual(version_get_response["data"]["status"], "published")

            links_response = call("factory.case_rule_link.list")
            self.assertEqual(links_response["data"]["link_count"], 1)

            rollback_response = call(
                "factory.rule_version.rollback",
                rule_version_id=rule_version_id,
                reason="api rollback",
            )
            self.assertTrue(rollback_response["ok"])
            self.assertEqual(rollback_response["data"]["rule_version"]["status"], "rolled_back")

            rollback_list_response = call("factory.rollback.list")
            self.assertEqual(rollback_list_response["data"]["rollback_count"], 1)

    def test_handle_request_feedback_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            record_response = handle_request(
                {
                    "action": "feedback.record",
                    "db_path": str(db_path),
                    "trace_id": "trace_feedback_001",
                    "route_decision": "exploration",
                    "feedback_type": "missed_rule",
                    "rule_ids": ["credit.loan_extension_notice.v1"],
                    "payload": {"reason": "no_direct_or_composable_rule"},
                    "case_id": "case_credit_loan_extension_notice_001",
                }
            )
            self.assertTrue(record_response["ok"])
            feedback_id = record_response["data"]["feedback_id"]

            list_response = handle_request(
                {
                    "action": "feedback.list",
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(list_response["ok"])
            self.assertEqual(list_response["data"]["feedback_count"], 1)

            get_response = handle_request(
                {
                    "action": "feedback.get",
                    "db_path": str(db_path),
                    "feedback_id": feedback_id,
                }
            )
            self.assertTrue(get_response["ok"])
            self.assertEqual(get_response["data"]["feedback_type"], "missed_rule")
            self.assertEqual(get_response["data"]["payload"]["classification"], "coverage_gap")
            self.assertEqual(get_response["data"]["payload"]["recommended_action"], "create_new_atomic_rule")
            self.assertEqual(get_response["data"]["payload"]["source_payload"]["reason"], "no_direct_or_composable_rule")

            promote_response = handle_request(
                {
                    "action": "factory.feedback.promote_to_draft",
                    "db_path": str(db_path),
                    "feedback_id": feedback_id,
                }
            )
            self.assertTrue(promote_response["ok"])
            self.assertEqual(promote_response["data"]["classification"]["recommended_action"], "create_new_atomic_rule")
            self.assertEqual(promote_response["data"]["draft"]["payload"]["asset_type"], "atomic_rule")
            self.assertEqual(promote_response["data"]["draft"]["payload"]["change_type"], "new")

            asset_view_response = handle_request(
                {
                    "action": "factory.retrieval_asset_view",
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(asset_view_response["ok"])
            self.assertEqual(asset_view_response["data"]["asset_count"], 0)

    def test_handle_request_rejects_invalid_factory_state_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            ingest_response = handle_request(
                {
                    "action": "factory.case.ingest",
                    "dataset_dir": str(DEMO_DATASET_DIR),
                    "db_path": str(db_path),
                }
            )
            case_id = ingest_response["data"]["case_id"]
            draft_response = handle_request(
                {
                    "action": "factory.draft.generate",
                    "case_id": case_id,
                    "db_path": str(db_path),
                }
            )
            draft_id = draft_response["data"]["draft_id"]
            review_response = handle_request(
                {
                    "action": "factory.review.create",
                    "draft_id": draft_id,
                    "db_path": str(db_path),
                }
            )
            review_task_id = review_response["data"]["review_task_id"]

            rejected = handle_request(
                {
                    "action": "factory.review.reject",
                    "review_task_id": review_task_id,
                    "db_path": str(db_path),
                }
            )
            self.assertTrue(rejected["ok"])

            approved = handle_request(
                {
                    "action": "factory.review.approve",
                    "review_task_id": review_task_id,
                    "db_path": str(db_path),
                }
            )
            self.assertFalse(approved["ok"])
            self.assertEqual(approved["error"]["code"], "bad_request")

    def test_handle_request_rejects_unsupported_action(self) -> None:
        response = handle_request({"action": "dataset.unknown"})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["code"], "unsupported_action")

    def test_handle_request_rejects_invalid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_dir = Path(tmpdir) / "broken_dataset"
            shutil.copytree(DEMO_DATASET_DIR, broken_dir)

            question_path = broken_dir / "question_struct.json"
            payload = json.loads(question_path.read_text(encoding="utf-8"))
            payload.pop("question_text")
            question_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            response = handle_request(
                {
                    "action": "dataset.import",
                    "dataset_dir": str(broken_dir),
                }
            )
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "invalid_dataset")


if __name__ == "__main__":
    unittest.main()
