from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from base64 import b64encode
from io import BytesIO
from pathlib import Path
import zipfile


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


def _make_pdf_bytes(text: str) -> bytes:
    objects = []
    objects.append('1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n')
    objects.append('2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n')
    objects.append('3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n')
    stream = f'BT\n/F1 12 Tf\n72 72 Td\n({text}) Tj\nET\n'
    objects.append(f'4 0 obj\n<< /Length {len(stream.encode())} >>\nstream\n{stream}endstream\nendobj\n')
    objects.append('5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n')
    content = '%PDF-1.4\n'
    offsets = []
    for obj in objects:
        offsets.append(len(content.encode('latin-1')))
        content += obj
    xref_offset = len(content.encode('latin-1'))
    content += f'xref\n0 {len(objects)+1}\n'
    content += '0000000000 65535 f \n'
    for offset in offsets:
        content += f'{offset:010d} 00000 n \n'
    content += f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n'
    return content.encode('latin-1')


from phase1_runtime.product import list_product_scenarios, solve_product_request, solve_workspace_request
from phase1_runtime.tests.mock_kimi import CREDIT_NOTICE_MOCK_VALUES, EQUITY_RESEARCH_MOCK_VALUES, FUND_NAV_MOCK_VALUES, MockKimiExtractor


class Phase1ProductServiceTests(unittest.TestCase):
    def test_list_product_scenarios(self) -> None:
        payload = list_product_scenarios()
        self.assertEqual(payload["default_scenario_id"], "fund_nav_warning")
        self.assertGreaterEqual(payload["scenario_count"], 2)

    def test_solve_product_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_product_request(
                scenario_id="credit_notice",
                question_text="是否需要发送借款人通知？",
                work_dir=tmpdir,
            )
            self.assertEqual(payload["scenario_id"], "credit_notice")
            self.assertEqual(payload["decision_text"], "建议发送借款人通知")
            self.assertEqual(payload["route_decision"], "rule_composable")
            self.assertEqual(payload["solution_view"]["execution"]["final_decision"], "must_notify")

    def test_solve_workspace_request_with_uploaded_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="是否需要发送借款人通知？",
                materials=[
                    {
                        "name": "notice_clause.txt",
                        "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                    }
                ],
                work_dir=tmpdir,
                kimi_client=MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES),
            )
            self.assertEqual(payload["scenario_id"], "credit_notice")
            # With signal detection, "到期" hint is found in the document, so routing
            # proceeds to direct_match. Mock Kimi extracts the values successfully.
            self.assertIn(payload["route_decision"], {"direct_match", "rule_composable", "needs_more_context"})
            self.assertGreater(len(payload["solution_view"]["execution"].get("final_answer", "")), 0)
            self.assertEqual(payload["input_mode"], "expert_workspace")
            self.assertEqual(payload["workspace_contract"]["entry_path"], "/workspace")
            self.assertEqual(payload["parser_bridge_status"], "runtime_connected")
            self.assertIn("embedding_backend", payload)
            self.assertIn("backend_id", payload["embedding_backend"])
            self.assertIn("task_context", payload)
            self.assertIn("rule_bindings", payload)
            self.assertIn("context_packet", payload)
            self.assertGreater(len(payload["context_packet"]["relevant_blocks"]), 0)
            self.assertIn("runtime_skill_spec_preview", payload)
            self.assertIn("runtime_skill_artifact", payload)
            self.assertIn("super_agent_handoff", payload)
            self.assertEqual(payload["super_agent_handoff"]["action"], "super_agent.run")
            self.assertTrue(payload["runtime_skill_artifact"]["root_path"].endswith(payload["runtime_skill_artifact"]["skill_name"]))
            self.assertTrue(Path(payload["runtime_skill_artifact"]["skill_md_path"]).exists())
            self.assertIn("validation", payload["runtime_skill_artifact"])
            self.assertGreaterEqual(len(payload["uploaded_materials"]), 1)
            self.assertGreaterEqual(len(payload["evidence_refs"]), 1)
            self.assertGreaterEqual(len(payload["fact_sheet"]), 1)
            self.assertEqual(payload["asset_pipeline"]["auto_status"], "recorded_only")
            self.assertEqual(payload["asset_pipeline"]["case"]["source"], "workspace_run")
            self.assertIsNotNone(payload["asset_pipeline"]["workspace_run"]["workspace_run_id"])
            self.assertIn("embedding_backend", payload["asset_pipeline"]["workspace_run"]["payload"])
            self.assertIn("task_context", payload["asset_pipeline"]["workspace_run"]["payload"])
            self.assertIn("rule_bindings", payload["asset_pipeline"]["workspace_run"]["payload"])
            self.assertIn("runtime_skill_spec_preview", payload["asset_pipeline"]["workspace_run"]["payload"])
            self.assertNotIn("runtime_skill_artifact", payload["asset_pipeline"]["workspace_run"]["payload"])

    def test_workspace_direct_match_with_missing_runtime_input_returns_needs_more_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="贷款展期前是否需要通知借款人？",
                materials=[
                    {
                        "name": "notice_clause.txt",
                        "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                    }
                ],
                work_dir=tmpdir,
                kimi_client=MockKimiExtractor(
                    {
                        "days_to_maturity": None,
                        "notice_threshold_days": 5,
                        "contract_requires_notice": True,
                    }
                ),
            )
            self.assertEqual(payload["route_decision"], "direct_match")
            self.assertEqual(payload["matched_rule_id"], "credit.loan_extension_notice.v1")
            self.assertEqual(payload["final_decision"], "needs_more_context")
            self.assertIn("days_to_maturity", payload["final_answer"])
            self.assertEqual(payload["missing_slots"], ["days_to_maturity"])
            self.assertEqual(payload["missing_slot_items"][0]["label"], "距离到期天数")

    def test_workspace_final_answer_prefers_super_agent_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch(
                "phase1_runtime.product.workspace_support.run_super_agent",
                return_value={
                    "final_text": "Super agent 最终回答：需要向借款人发送通知。",
                    "turns": 2,
                    "tool_call_count": 1,
                    "history": [],
                },
            ):
                payload = solve_workspace_request(
                    question_text="是否需要发送借款人通知？",
                    materials=[
                        {
                            "name": "notice_clause.txt",
                            "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                        }
                    ],
                    work_dir=tmpdir,
                    kimi_client=MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES),
                )
            self.assertEqual(payload["answer_engine"], "super_agent")
            self.assertEqual(payload["solution_view"]["execution"]["answer_engine"], "super_agent")
            self.assertIn("Super agent 最终回答", payload["final_answer"])
            self.assertIsNotNone(payload["super_agent_result"])

    def test_solve_workspace_request_with_binary_docx_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "isolated.db"  # isolated DB to prevent shortcut interference
            payload = solve_workspace_request(
                question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                materials=[
                    {
                        "name": "fund_clause.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。",
                            "最新单位净值为0.72。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
            )
            self.assertEqual(payload["scenario_id"], "fund_nav_warning")
            self.assertEqual(payload["decision_text"], "需要进行风险提示")
            self.assertEqual(payload["parser_bridge_status"], "runtime_connected")
            self.assertGreaterEqual(len(payload["fact_sheet"]), 1)
            self.assertEqual(payload["uploaded_materials"][0]["parse_status"], "parsed_docx_text")
            self.assertEqual(payload["orchestration_view"]["planner"]["planner_mode"], "direct_rule_planner")
            self.assertGreaterEqual(payload["orchestration_view"]["planner"]["template_count"], 1)
            self.assertGreaterEqual(payload["orchestration_view"]["planner"]["skill_count"], 1)
            self.assertIsNotNone(payload["runtime_skill_spec_preview"])
            self.assertEqual(payload["runtime_skill_spec_preview"]["source_rule_id"], "private_fund.nav_risk_warning.v1")
            self.assertIsNotNone(payload["runtime_skill_artifact"])
            self.assertEqual(payload["runtime_skill_artifact"]["source_rule_id"], "private_fund.nav_risk_warning.v1")
            self.assertIn("validation", payload["runtime_skill_artifact"])

    def test_solve_workspace_request_with_binary_pdf_material(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "isolated.db"
            with patch(
                "phase1_runtime.parsing.document_parser_mvp.understand_pdf_bytes",
                return_value={
                    "title": "Fund Clause PDF",
                    "document_family": "fund_notice_report",
                    "blocks": [
                        {
                            "block_id": "block_001",
                            "block_type": "paragraph",
                            "section": "body",
                            "page": 1,
                            "text": "基金合同约定当产品净值低于0.80时应及时提示风险。最新单位净值为0.72。",
                        }
                    ],
                    "semantic_signals": [],
                },
            ):
                payload = solve_workspace_request(
                    question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                    materials=[
                        {
                            "name": "fund_clause.pdf",
                            "content_base64": b64encode(_make_pdf_bytes(
                                "Contract requires warning below 0.80. Current NAV is 0.72."
                            )).decode("ascii"),
                        }
                    ],
                    work_dir=tmpdir,
                    db_path=db_path,
                    kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
                )
            self.assertEqual(payload["scenario_id"], "fund_nav_warning")
            self.assertEqual(payload["parser_bridge_status"], "runtime_connected")
            self.assertEqual(payload["uploaded_materials"][0]["parse_status"], "parsed_pdf_kimi")
            self.assertEqual(payload["document_packet_preview"]["documents"][0]["source_type"], "uploaded_pdf")
            self.assertEqual(payload["document_packet_preview"]["documents"][0]["parse_status"], "parsed_pdf_kimi")
            self.assertIn(payload["route_decision"], {"direct_match", "rule_composable", "needs_more_context", "exploration"})
            self.assertIsNone(payload["shortcut_case"])
            self.assertFalse(payload["trace_id"].startswith("shortcut_"))

    def test_workspace_run_auto_promotes_exploration_to_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="请给出处理意见。",
                materials=[],
                scenario_id="fund_nav_warning",
                work_dir=tmpdir,
                db_path=Path(tmpdir) / "registry.db",
            )
            self.assertEqual(payload["route_decision"], "exploration")
            self.assertIsNotNone(payload["exploration_runtime"])
            self.assertEqual(payload["exploration_runtime"]["status"], "exploration_pending")
            self.assertIsNotNone((payload["exploration_runtime"].get("external_task") or {}).get("task_id"))
            self.assertEqual(payload["orchestration_view"]["planner"]["planner_mode"], "exploration_planner")
            self.assertGreaterEqual(payload["orchestration_view"]["planner"]["template_count"], 1)
            self.assertEqual(payload["asset_pipeline"]["auto_status"], "draft_promoted")
            self.assertIsNotNone(payload["asset_pipeline"]["feedback"])
            self.assertIsNotNone(payload["asset_pipeline"]["promotion"])
            self.assertIsNotNone(payload["asset_pipeline"]["review"])
            self.assertEqual(payload["asset_pipeline"]["promotion"]["draft"]["status"], "draft")
            self.assertIn("test_execution_preview", payload["asset_pipeline"]["review"]["payload"])

    def test_workspace_exploration_defaults_to_multi_agent_backend_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mocked_exploration = {
                "exploration_trace_id": "task_mocked_external",
                "mode": "multi_agent_exploration_emergent",
                "trigger_reason": "no_direct_or_composable_rule",
                "route_entry": "exploration",
                "case_draft": {
                    "case_draft_id": "case_draft_mocked_external",
                    "summary": "外部探索系统已给出候选解法。",
                },
                "candidate_rule_drafts": [
                    {
                        "draft_type": "candidate_adapted_rule_draft",
                        "recommended_action": "create_or_patch_composite_rule",
                        "based_on_rule_ids": ["private_fund.nav_risk_warning.v1"],
                        "summary": "建议在现有方法上补充新的适用范围。",
                    }
                ],
                "evidence_pattern_suggestions": [],
                "validator_pattern_suggestions": [],
                "recommended_feedback_type": "missed_rule",
                "recommended_rule_ids": ["private_fund.nav_risk_warning.v1"],
            }
            with patch(
                "phase1_runtime.product.workspace_support.run_multi_agent_exploration",
                return_value=mocked_exploration,
            ) as mocked:
                payload = solve_workspace_request(
                    question_text="请给出处理意见。",
                    materials=[],
                    scenario_id="fund_nav_warning",
                    work_dir=tmpdir,
                    db_path=Path(tmpdir) / "registry.db",
                    block_until_complete=True,
                )
            mocked.assert_called_once()
            self.assertEqual(payload["route_decision"], "exploration")
            self.assertEqual(payload["exploration_runtime"]["mode"], "multi_agent_exploration_emergent")
            self.assertEqual(payload["exploration_runtime"]["candidate_rule_drafts"][0]["recommended_action"], "create_or_patch_composite_rule")

    def test_workspace_exploration_falls_back_to_builtin_when_external_backend_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mocked_builtin = {
                "exploration_trace_id": "exploration_builtin_trace",
                "mode": "builtin_exploration",
                "route_entry": "exploration",
                "recommended_feedback_type": "missed_rule",
                "recommended_rule_ids": ["private_fund.nav_risk_warning.v1"],
                "candidate_rule_drafts": [],
            }
            with patch(
                "phase1_runtime.product.workspace_support.run_multi_agent_exploration",
                side_effect=RuntimeError("external exploration failed"),
            ) as external_mock, patch(
                "phase1_runtime.product.workspace_support.run_exploration_runtime",
                return_value=mocked_builtin,
            ) as builtin_mock:
                payload = solve_workspace_request(
                    question_text="请给出处理意见。",
                    materials=[],
                    scenario_id="fund_nav_warning",
                    work_dir=tmpdir,
                    db_path=Path(tmpdir) / "registry.db",
                    block_until_complete=True,
                )
            external_mock.assert_called_once()
            builtin_mock.assert_called_once()
            self.assertEqual(payload["route_decision"], "exploration")
            self.assertEqual(payload["exploration_runtime"]["mode"], "builtin_exploration")
            self.assertEqual(payload["exploration_runtime"]["external_backend"], "multi_agent_exploration")
            self.assertIn("external_backend_error", payload["exploration_runtime"])

    def test_workspace_exploration_runs_provisional_super_agent_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mocked_exploration = {
                "exploration_trace_id": "task_mocked_external",
                "mode": "multi_agent_exploration_emergent",
                "trigger_reason": "no_direct_or_composable_rule",
                "route_entry": "exploration",
                "case_draft": {
                    "case_draft_id": "case_draft_mocked_external",
                    "summary": "外部探索系统已形成一份临时方法草稿。",
                },
                "candidate_rule_drafts": [
                    {
                        "draft_type": "candidate_novel_rule_draft",
                        "recommended_action": "create_new_atomic_rule",
                        "summary": "先基于文档证据形成探索性结论。",
                        "rule_title": "探索性结论方法",
                        "rule_text": "当现有规则无法覆盖时，先基于当前文档证据生成探索性答案，并标记为待人工确认。",
                    }
                ],
                "recommended_feedback_type": "missed_rule",
                "recommended_rule_ids": [],
                "external_task": {
                    "task_id": "task_mocked_external",
                    "discovery_mode": "emergent",
                    "metadata": {"use_llm": True},
                },
                "external_result": {
                    "open_questions": ["仍需人工确认适用边界。"],
                },
            }
            with patch(
                "phase1_runtime.product.workspace_support.run_multi_agent_exploration",
                return_value=mocked_exploration,
            ), patch(
                "phase1_runtime.product.workspace_support.run_super_agent",
                return_value={
                    "final_text": "探索性答案：根据当前材料，研报对工商银行维持增持观点。",
                    "turns": 2,
                    "tool_call_count": 0,
                    "history": [],
                    "agent_trace": [],
                },
            ) as agent_mock:
                payload = solve_workspace_request(
                    question_text="这份研报对工商银行的投资评级是什么？",
                    materials=[],
                    scenario_id="equity_research",
                    work_dir=tmpdir,
                    db_path=Path(tmpdir) / "registry.db",
                    block_until_complete=True,
                    run_live_super_agent=True,
                )
            agent_mock.assert_called_once()
            self.assertEqual(payload["route_decision"], "exploration")
            self.assertEqual(payload["answer_engine"], "super_agent")
            self.assertIn("探索性答案", payload["final_answer"])
            self.assertIsNotNone(payload["runtime_skill_artifact"])
            self.assertEqual(payload["runtime_skill_spec_preview"]["skill_type"], "exploration_provisional")
            self.assertEqual(payload["display_decision_text"], "已生成探索性答案")

    def test_workspace_run_known_family_gap_prefers_patch_existing_rule(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mocked_exploration = {
                "exploration_trace_id": "task_known_family_gap",
                "mode": "multi_agent_exploration_emergent",
                "route_entry": "exploration",
                "trigger_reason": "no_direct_or_composable_rule",
                "case_draft": {
                    "case_draft_id": "case_draft_known_family",
                    "summary": "现有规则可补丁式扩展。",
                },
                "candidate_rule_drafts": [
                    {
                        "recommended_action": "patch_existing_rule_scope",
                        "summary": "建议在现有方法上补充新的适用范围。",
                        "rule_id": "private_fund.nav_risk_warning.v1",
                    }
                ],
                "evidence_pattern_suggestions": [{"type": "numeric_range"}],
                "validator_pattern_suggestions": [{"type": "include_scope"}],
                "recommended_feedback_type": "workspace_observation",
                "recommended_rule_ids": ["private_fund.nav_risk_warning.v1"],
            }
            with patch(
                "phase1_runtime.product.workspace_support.run_multi_agent_exploration",
                return_value=mocked_exploration,
            ):
                payload = solve_workspace_request(
                    question_text="请给出处理意见。",
                    materials=[
                        {
                            "name": "fund_clause.docx",
                            "content_base64": b64encode(_make_docx_bytes([
                                "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。",
                                "最新单位净值为0.72。",
                            ])).decode("ascii"),
                        }
                    ],
                    scenario_id="fund_nav_warning",
                    work_dir=tmpdir,
                    db_path=Path(tmpdir) / "registry.db",
                    block_until_complete=True,
                )
            self.assertEqual(payload["route_decision"], "exploration")
            self.assertIsNotNone(payload["exploration_runtime"])
            self.assertEqual(payload["asset_pipeline"]["auto_status"], "draft_promoted")
            self.assertEqual(payload["asset_pipeline"]["feedback"]["payload"]["recommended_action"], "patch_existing_rule_scope")
            self.assertEqual(payload["asset_pipeline"]["promotion"]["draft"]["proposed_rule_id"], "private_fund.nav_risk_warning.v1")
            self.assertEqual(payload["asset_pipeline"]["promotion"]["draft"]["payload"]["patch_target"]["patch_type"], "scope")

    def test_binary_docx_auto_routes_credit_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="是否需要发送借款人通知？",
                materials=[
                    {
                        "name": "notice_clause.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "合同约定在到期前5日内应通知借款人办理展期手续。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
            )
            self.assertEqual(payload["scenario_id"], "credit_notice")
            self.assertEqual(payload["uploaded_materials"][0]["parse_status"], "parsed_docx_text")

    def test_workspace_preview_preserves_docx_parse_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                materials=[
                    {
                        "name": "fund_clause.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。",
                            "最新单位净值为0.72。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
            )
            self.assertEqual(payload["document_packet_preview"]["documents"][0]["source_type"], "uploaded_docx")
            self.assertEqual(payload["document_packet_preview"]["documents"][0]["parse_status"], "parsed_docx_text")
            self.assertTrue(all(ref["doc_id"] != "question_input" for ref in payload["evidence_refs"]))

    def test_workspace_auto_routes_equity_research_scenario(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "isolated.db"
            payload = solve_workspace_request(
                question_text="",
                materials=[
                    {
                        "name": "research_report.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "证券研究报告：工商银行（601398）公司简评。",
                            "维持增持评级，目标价8.6元，基于0.75x 2026E PB。",
                            "下行风险：零售不良超预期，LPR再度大幅下调，债市急跌导致投资收益亏损。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(EQUITY_RESEARCH_MOCK_VALUES),
            )
            self.assertEqual(payload["scenario_id"], "equity_research")
            self.assertEqual(payload["route_decision"], "direct_match")
            self.assertEqual(payload["final_decision"], "rating_bullish")
            self.assertEqual(payload["decision_text"], "研报观点偏积极")
            self.assertEqual(payload["uploaded_materials"][0]["parse_status"], "parsed_docx_text")
            self.assertEqual(payload["document_packet_preview"]["documents"][0]["doc_type"], "report")
            self.assertIsNotNone(payload["runtime_skill_spec_preview"])
            self.assertEqual(payload["runtime_skill_spec_preview"]["source_rule_id"], "equity_research.full_analysis.v1")

    def test_workspace_answers_equity_research_risk_count_question(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "isolated.db"
            payload = solve_workspace_request(
                question_text="这份研报列出了几项主要下行风险？",
                materials=[
                    {
                        "name": "research_report.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "证券研究报告：工商银行（601398）公司简评。",
                            "维持增持评级，目标价8.6元，基于0.75x 2026E PB。",
                            "风险提示：①零售不良超预期；②LPR再度大幅下调；③债市急跌导致投资收益亏损。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(EQUITY_RESEARCH_MOCK_VALUES),
            )
            self.assertEqual(payload["scenario_id"], "equity_research")
            self.assertEqual(payload["route_decision"], "direct_match")
            self.assertEqual(payload["final_decision"], "risk_count_answered")
            self.assertIn("3 项", payload["final_answer"])

    def test_workspace_rule_bindings_include_fact_hit_reasons_from_signal_fact_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "isolated.db"
            payload = solve_workspace_request(
                question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
                materials=[
                    {
                        "name": "fund_clause.docx",
                        "content_base64": b64encode(_make_docx_bytes([
                            "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。",
                            "最新单位净值为0.72。",
                        ])).decode("ascii"),
                    }
                ],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
            )
            self.assertTrue(
                any(
                    any(reason.startswith("required_fact_hits=") for reason in binding["reasons"])
                    for binding in payload["rule_bindings"]
                )
            )

    def test_workspace_shortcut_still_applies_without_uploaded_materials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            seeded = solve_workspace_request(
                question_text="借款距到期20天，合同约定前30天通知，是否需要发送通知？",
                materials=[
                    {
                        "name": "notice.txt",
                        "content": "贷款到期前30日内应通知借款人。剩余20天。",
                    }
                ],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES),
            )
            self.assertIsNone(seeded["shortcut_case"])

            payload = solve_workspace_request(
                question_text="借款距到期20天，合同约定前30天通知，是否需要发送通知？",
                materials=[],
                work_dir=tmpdir,
                db_path=db_path,
            )
            self.assertIsNotNone(payload["shortcut_case"])
            self.assertTrue(payload["trace_id"].startswith("shortcut_"))
            self.assertEqual(payload["final_decision"], seeded["final_decision"])


if __name__ == "__main__":
    unittest.main()
