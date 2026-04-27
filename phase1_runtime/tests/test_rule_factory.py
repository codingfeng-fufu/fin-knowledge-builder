from __future__ import annotations

from base64 import b64encode
from io import BytesIO
from pathlib import Path
import zipfile
import tempfile
import unittest
from unittest.mock import patch

from phase1_runtime.product import solve_workspace_request
from phase1_runtime.tests.mock_kimi import FUND_NAV_MOCK_VALUES, MockKimiExtractor
from phase1_runtime.factory import (
    approve_review,
    create_review_for_draft,
    generate_candidate_rule_draft,
    get_case,
    get_review,
    promote_feedback_to_draft,
    record_feedback,
    retrieval_asset_view_service,
    get_rule_draft,
    get_rule_version_service,
    ingest_case_from_dataset,
    list_case_rule_links_service,
    list_cases,
    list_reviews,
    list_rollbacks_service,
    list_rule_drafts,
    list_rule_versions_service,
    reject_review,
    rollback_rule_version_service,
)
from phase1_runtime.factory import RuleFactoryError


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



class Phase1RuleFactoryTests(unittest.TestCase):
    def test_publish_and_rollback_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            self.assertEqual(case["dataset_id"], "demo_set_001")

            cases = list_cases(db_path=db_path)
            self.assertEqual(cases["case_count"], 1)
            fetched_case = get_case(case["case_id"], db_path=db_path)
            self.assertEqual(fetched_case["question_text"], case["question_text"])

            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            self.assertEqual(draft["status"], "draft")
            self.assertEqual(draft["payload"]["provenance"]["source_case_id"], case["case_id"])
            self.assertEqual(draft["payload"]["asset_type"], "composite_rule")
            self.assertEqual(draft["payload"]["asset_id"], "private_fund.nav_risk_warning.v1")
            self.assertEqual(draft["payload"]["change_type"], "patch")
            self.assertEqual(draft["payload"]["source_trace_ids"], [case["payload"]["source_trace_id"]])
            self.assertEqual(draft["payload"]["based_on_asset_ids"], ["private_fund.nav_risk_warning.v1"])

            drafts = list_rule_drafts(db_path=db_path)
            self.assertEqual(drafts["draft_count"], 1)
            fetched_draft = get_rule_draft(draft["draft_id"], db_path=db_path)
            self.assertEqual(fetched_draft["proposed_rule_id"], draft["proposed_rule_id"])

            review = create_review_for_draft(draft["draft_id"], assignee="qa_reviewer", db_path=db_path)
            self.assertEqual(review["status"], "open")
            self.assertEqual(review["assignee"], "qa_reviewer")
            self.assertIn("embedding_backend", review["payload"])
            self.assertIn("runtime_skill_spec_preview", review["payload"])

            reviews = list_reviews(db_path=db_path)
            self.assertEqual(reviews["review_count"], 1)
            fetched_review = get_review(review["review_task_id"], db_path=db_path)
            self.assertEqual(fetched_review["draft_id"], draft["draft_id"])
            self.assertIn("embedding_backend", fetched_review["payload"])
            self.assertIn("runtime_skill_spec_preview", fetched_review["payload"])
            self.assertEqual(get_rule_draft(draft["draft_id"], db_path=db_path)["status"], "under_review")

            approval = approve_review(review["review_task_id"], note="approved for publish", db_path=db_path)
            rule_version_id = approval["rule_version"]["rule_version_id"]
            self.assertEqual(approval["review"]["status"], "approved")
            self.assertEqual(approval["rule_version"]["status"], "published")
            self.assertIn("rule_graph_artifacts", approval)
            self.assertTrue(Path(approval["rule_graph_artifacts"]["artifact_root"]).exists())
            self.assertEqual(
                approval["rule_graph_artifacts"]["output_dir"],
                str((Path(tmpdir) / "rule_graph").resolve()),
            )

            versions = list_rule_versions_service(db_path=db_path)
            self.assertEqual(versions["rule_version_count"], 1)
            version = get_rule_version_service(rule_version_id, db_path=db_path)
            self.assertEqual(version["payload"]["approved_note"], "approved for publish")
            self.assertEqual(version["payload"]["asset_type"], "composite_rule")
            self.assertEqual(version["payload"]["asset_id"], "private_fund.nav_risk_warning.v1")
            self.assertEqual(version["payload"]["change_type"], "patch")
            self.assertIn("embedding_backend", version["payload"])
            self.assertIn("runtime_skill_spec_preview", version["payload"])
            self.assertEqual(version["payload"]["source_trace_ids"], [case["payload"]["source_trace_id"]])
            self.assertEqual(version["payload"]["based_on_asset_ids"], ["private_fund.nav_risk_warning.v1"])
            self.assertIsNone(version["payload"]["supersedes_rule_version_id"])
            self.assertTrue(version["payload"]["source_validation"]["validation_passed"])
            self.assertEqual(version["payload"]["source_validation"]["matched_rule_id"], "private_fund.nav_risk_warning.v1")

            links = list_case_rule_links_service(db_path=db_path)
            self.assertEqual(links["link_count"], 1)
            self.assertEqual(links["links"][0]["case_id"], case["case_id"])

            rollback = rollback_rule_version_service(rule_version_id, reason="superseded", db_path=db_path)
            self.assertEqual(rollback["rule_version"]["status"], "rolled_back")
            self.assertEqual(rollback["rollback"]["reason"], "superseded")
            self.assertIn("rule_graph_artifacts", rollback)
            self.assertTrue(Path(rollback["rule_graph_artifacts"]["artifact_root"]).exists())

            rollbacks = list_rollbacks_service(db_path=db_path)
            self.assertEqual(rollbacks["rollback_count"], 1)

    def test_approve_rejected_review_fails_publish_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            reject_review(review["review_task_id"], db_path=db_path)

            with self.assertRaises(RuleFactoryError):
                approve_review(review["review_task_id"], db_path=db_path)

    def test_promote_feedback_to_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=["credit.loan_extension_notice.v1"],
                payload={"reason": "missed reusable atomic rule"},
                db_path=db_path,
            )

            promoted = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            draft = promoted["draft"]
            self.assertEqual(promoted["classification"]["classification"], "coverage_gap")
            self.assertEqual(promoted["classification"]["recommended_action"], "create_new_atomic_rule")
            self.assertEqual(draft["payload"]["asset_type"], "atomic_rule")
            self.assertEqual(draft["payload"]["change_type"], "new")
            self.assertEqual(draft["payload"]["source_trace_ids"], [case["payload"]["source_trace_id"]])
            self.assertEqual(draft["payload"]["based_on_asset_ids"], ["credit.loan_extension_notice.v1"])
            self.assertEqual(draft["payload"]["feedback_context"]["feedback_id"], feedback["feedback_id"])
            self.assertIn("embedding_backend", draft["payload"])
            self.assertIn("runtime_skill_spec_preview", draft["payload"])

    def test_reject_review_reruns_multi_agent_exploration_and_opens_new_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            source_payload = {
                "entry": "workspace",
                "scenario_id": "credit_notice",
                "question_text": "面对表述模糊、可能误导借款人的展期通知，应如何处理？",
                "runtime_status": "failed",
                "final_decision": "needs_review",
                "parser_status": "parsed_complete",
                "missing_fact_keys": ["notice_window_days"],
                "fact_sheet": [],
                "document_packet_preview": {
                    "documents": [{"doc_id": "upload_doc_001", "title": "notice.txt"}],
                },
                "exploration_runtime": {
                    "exploration_trace_id": "task_seeded_external",
                    "mode": "multi_agent_exploration_emergent",
                    "recommended_feedback_type": "missed_rule",
                    "recommended_rule_ids": ["credit.loan_extension_notice.v1"],
                    "candidate_rule_drafts": [
                        {
                            "recommended_action": "create_new_atomic_rule",
                        }
                    ],
                    "external_task": {
                        "task_id": "task_seeded_external",
                        "discovery_mode": "emergent",
                        "metadata": {"use_llm": True},
                    },
                },
            }
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=["credit.loan_extension_notice.v1"],
                payload=source_payload,
                db_path=db_path,
            )
            draft = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)["draft"]
            review = create_review_for_draft(draft["draft_id"], assignee="ops_reviewer", db_path=db_path)

            mocked_rerun = {
                "exploration_trace_id": "task_rerun_external",
                "mode": "multi_agent_exploration_emergent",
                "recommended_feedback_type": "missed_rule",
                "recommended_rule_ids": ["credit.loan_extension_notice.v1"],
                "candidate_rule_drafts": [
                    {
                        "draft_type": "candidate_atomic_rule_draft",
                        "recommended_action": "create_new_atomic_rule",
                        "based_on_rule_ids": ["credit.loan_extension_notice.v1"],
                        "summary": "根据审核反馈已重新生成候选解法。",
                    }
                ],
                "external_task": {
                    "task_id": "task_rerun_external",
                    "discovery_mode": "emergent",
                    "metadata": {"use_llm": True},
                },
            }
            with patch(
                "phase1_runtime.factory.rule_factory_review_flow.rerun_multi_agent_exploration",
                return_value=mocked_rerun,
            ) as mocked:
                result = reject_review(review["review_task_id"], note="当前规则不具备通用性，请重新生成。", db_path=db_path)

            mocked.assert_called_once()
            self.assertEqual(result["review"]["status"], "rejected")
            self.assertEqual(result["draft"]["status"], "rejected")
            self.assertIn("rerun", result)
            self.assertEqual(result["rerun"]["feedback"]["feedback_type"], "missed_rule")
            self.assertEqual(result["rerun"]["promotion"]["draft"]["status"], "draft")
            self.assertEqual(result["rerun"]["review"]["status"], "open")
            self.assertEqual(result["rerun"]["review"]["assignee"], "ops_reviewer")


    def test_promote_composition_feedback_to_composite_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="rule_composable",
                feedback_type="composition_failure",
                rule_ids=[
                    "atomic.numeric_threshold_breach.v1",
                    "atomic.contractual_warning_gate.v1",
                    "atomic.policy_answer_builder.v1",
                ],
                payload={"reason": "stable composition should become a published composite rule", "composition_pattern": "derive_then_decide"},
                db_path=db_path,
            )

            promoted = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            draft = promoted["draft"]
            self.assertEqual(promoted["classification"]["classification"], "composition_gap")
            self.assertEqual(promoted["classification"]["recommended_action"], "create_or_patch_composite_rule")
            self.assertEqual(draft["payload"]["asset_type"], "composite_rule")
            self.assertEqual(draft["payload"]["change_type"], "new")
            self.assertIn("embedding_backend", draft["payload"])
            self.assertIn("runtime_skill_spec_preview", draft["payload"])
            self.assertTrue(draft["proposed_rule_id"].startswith("composite.generated."))
            self.assertEqual(draft["payload"]["based_on_asset_ids"], [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])
            self.assertEqual(draft["payload"]["composition"]["pattern"], "derive_then_decide")
            self.assertEqual(draft["payload"]["composition"]["source_rule_ids"], [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])

            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            self.assertIn("embedding_backend", review["payload"])
            self.assertIn("runtime_skill_spec_preview", review["payload"])
            approval = approve_review(review["review_task_id"], db_path=db_path)
            version = approval["rule_version"]
            self.assertEqual(version["payload"]["asset_type"], "composite_rule")
            self.assertEqual(version["payload"]["change_type"], "new")
            self.assertIn("embedding_backend", version["payload"])
            self.assertIn("runtime_skill_spec_preview", version["payload"])
            self.assertEqual(version["payload"]["based_on_asset_ids"], [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])
            self.assertEqual(version["payload"]["rule"]["composition"]["pattern"], "derive_then_decide")

            asset_view = retrieval_asset_view_service(db_path=db_path)
            self.assertEqual(asset_view["asset_count"], 1)
            asset = asset_view["assets"][0]
            self.assertEqual(asset["asset_type"], "composite_rule")
            self.assertEqual(asset["change_type"], "new")
            self.assertEqual(asset["composition"]["pattern"], "derive_then_decide")
            self.assertEqual(asset["based_on_asset_ids"], [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])

    def test_known_family_missed_rule_prefers_patch_existing_asset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=["private_fund.nav_risk_warning.v1"],
                payload={
                    "parser_status": "parsed_complete",
                    "missing_fact_keys": [],
                    "reason": "known family but current rule scope missed the case",
                },
                db_path=db_path,
            )

            self.assertEqual(feedback["payload"]["recommended_action"], "patch_existing_rule_scope")
            self.assertEqual(feedback["payload"]["decision_reason"], "known_family_without_missing_facts")

            promoted = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            draft = promoted["draft"]
            self.assertEqual(draft["proposed_rule_id"], "private_fund.nav_risk_warning.v1")
            self.assertEqual(draft["payload"]["change_type"], "patch")
            self.assertEqual(draft["payload"]["patch_target"]["patch_type"], "scope")
            self.assertEqual(draft["payload"]["feedback_context"]["decision_reason"], "known_family_without_missing_facts")
            self.assertIn("embedding_backend", draft["payload"])
            self.assertIn("runtime_skill_spec_preview", draft["payload"])

    def test_insufficient_evidence_feedback_patches_existing_rule_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"

            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="direct_match",
                feedback_type="insufficient_evidence",
                rule_ids=["credit.loan_extension_notice.v1"],
                payload={"reason": "need stronger evidence locator pattern"},
                db_path=db_path,
            )

            self.assertEqual(feedback["payload"]["recommended_action"], "patch_evidence_pattern")
            self.assertEqual(feedback["payload"]["decision_reason"], "existing_asset_needs_evidence_patch")

            promoted = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            draft = promoted["draft"]
            self.assertEqual(draft["proposed_rule_id"], "credit.loan_extension_notice.v1")
            self.assertEqual(draft["payload"]["change_type"], "patch")
            self.assertEqual(draft["payload"]["patch_target"]["patch_type"], "evidence_pattern")
            self.assertIn("embedding_backend", draft["payload"])
            self.assertIn("runtime_skill_spec_preview", draft["payload"])

    def test_promote_feedback_to_draft_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=["credit.loan_extension_notice.v1"],
                payload={"reason": "idempotence check"},
                db_path=db_path,
            )
            first = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            second = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)
            self.assertEqual(first["draft"]["draft_id"], second["draft"]["draft_id"])
            self.assertTrue(second["reused_existing_draft"])

    def test_create_review_for_draft_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            first = create_review_for_draft(draft["draft_id"], db_path=db_path)
            second = create_review_for_draft(draft["draft_id"], db_path=db_path)
            self.assertEqual(first["review_task_id"], second["review_task_id"])

    def test_create_review_for_draft_includes_three_layer_execution_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            preview = review["payload"]["test_execution_preview"]
            self.assertIn("runtime_preview", preview)
            self.assertIn("method_draft_preview", preview)
            self.assertIn("agent_preview", preview)
            self.assertIn("status", preview["runtime_preview"])

    def test_rollback_rule_version_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            approval = approve_review(review["review_task_id"], db_path=db_path)
            version_id = approval["rule_version"]["rule_version_id"]
            first = rollback_rule_version_service(version_id, reason='cleanup', db_path=db_path)
            second = rollback_rule_version_service(version_id, reason='cleanup', db_path=db_path)
            self.assertEqual(first["rollback"]["rollback_id"], second["rollback"]["rollback_id"])
            self.assertIn("rule_graph_artifacts", first)
            self.assertIn("rule_graph_artifacts", second)

    def test_workspace_generated_patch_draft_can_publish(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
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
                scenario_id="fund_nav_warning",
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=MockKimiExtractor(FUND_NAV_MOCK_VALUES),
            )
            case_id = payload["asset_pipeline"]["case"]["case_id"]
            feedback = record_feedback(
                trace_id=payload["trace_id"],
                case_id=case_id,
                route_decision="direct_match",
                feedback_type="insufficient_evidence",
                rule_ids=["private_fund.nav_risk_warning.v1"],
                payload={"reason": "need stronger evidence locator pattern for workspace case"},
                db_path=db_path,
            )
            draft = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)["draft"]
            self.assertIn("embedding_backend", draft["payload"])
            self.assertIn("runtime_skill_spec_preview", draft["payload"])
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            self.assertIn("embedding_backend", review["payload"])
            self.assertIn("runtime_skill_spec_preview", review["payload"])
            approval = approve_review(review["review_task_id"], db_path=db_path)
            self.assertEqual(approval["rule_version"]["status"], "published")
            self.assertEqual(approval["rule_version"]["payload"]["asset_id"], "private_fund.nav_risk_warning.v1")
            self.assertIn("embedding_backend", approval["rule_version"]["payload"])
            self.assertIn("runtime_skill_spec_preview", approval["rule_version"]["payload"])

    def test_exploration_generated_draft_can_publish_when_selection_is_not_direct(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            case = ingest_case_from_dataset(CREDIT_DATASET_DIR, db_path=db_path)
            feedback = record_feedback(
                trace_id=case["payload"]["source_trace_id"],
                case_id=case["case_id"],
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=[],
                payload={
                    "scenario_id": "equity_research",
                    "question_text": "这份研报对工商银行的投资评级是什么？",
                    "question_packet_preview": {
                        "question_types": ["analysis_query"],
                        "intents": ["extract", "summarize"],
                        "document_types": ["report"],
                    },
                    "exploration_runtime": {
                        "candidate_rule_drafts": [
                            {
                                "draft_type": "candidate_novel_rule_draft",
                                "recommended_action": "create_new_atomic_rule",
                                "rule_title": "探索性结论方法",
                                "rule_text": "先基于当前证据生成探索性答案。",
                                "summary": "探索系统形成了一份候选方法。",
                            }
                        ]
                    },
                },
                db_path=db_path,
            )
            draft = promote_feedback_to_draft(feedback["feedback_id"], db_path=db_path)["draft"]
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            approval = approve_review(review["review_task_id"], db_path=db_path)
            self.assertEqual(approval["review"]["status"], "approved")
            self.assertEqual(approval["rule_version"]["status"], "published")
            self.assertTrue(approval["rule_version"]["payload"]["source_validation"]["selection_tolerated"])


if __name__ == "__main__":
    unittest.main()
