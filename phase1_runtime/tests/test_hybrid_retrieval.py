from __future__ import annotations

import json
from pathlib import Path
import unittest

from phase1_runtime.retrieval import build_retrieval_query, build_rule_asset_index, retrieve_hybrid_matches_from_rules, semantic_similarity
from phase1_runtime.schema import EvidenceRef, QuestionStruct, Rule, load_document_bundle, load_question, load_rule


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _clone_rule(path: Path, *, rule_id: str, required_inputs: list[str], query_signals: list[str] | None = None) -> Rule:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rule_id"] = rule_id
    payload["name"] = f"cloned::{rule_id}"
    if query_signals is not None:
        payload["trigger"]["query_signals"] = list(query_signals)
    payload["inputs"]["required"] = [
        {
            "key": key,
            "type": "number" if "nav" in key or "threshold" in key else "boolean",
            "description": key,
        }
        for key in required_inputs
    ]
    return Rule.from_dict(payload)


class HybridRetrievalTests(unittest.TestCase):
    def test_semantic_similarity_scores_related_text_higher(self) -> None:
        related = semantic_similarity(
            "某私募产品单位份额价格触发合同警戒线后，是否需要向持有人提示？",
            "适用于私募产品净值跌破合同阈值后是否需要向投资者提示风险的判断。",
        )
        unrelated = semantic_similarity(
            "某私募产品单位份额价格触发合同警戒线后，是否需要向持有人提示？",
            "适用于贷款展期是否需要向借款人发送通知的判断。",
        )
        self.assertGreater(related, unrelated)

    def test_build_retrieval_query_includes_fact_keys_and_evidence_terms(self) -> None:
        question = QuestionStruct(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            question_types=["policy_check"],
            intents=["compare", "judge"],
            document_types=["contract", "policy"],
            extracted_inputs={},
        )
        query = build_retrieval_query(
            question,
            facts={"current_nav": 0.72, "warning_threshold": 0.8},
            evidence_refs=[EvidenceRef(doc_id="doc_001", locator={}, snippet_id="snippet_nav_table", text="最新单位净值为0.72。")],
        )
        self.assertIn("current_nav", query.fact_keys)
        self.assertIn("warning_threshold", query.fact_keys)
        self.assertIn("最新单位净值为", query.evidence_terms)
        self.assertIn("0.72", query.evidence_terms)

    def test_build_retrieval_query_accepts_signal_fact_keys_without_runtime_fact_values(self) -> None:
        question = QuestionStruct(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            question_types=["policy_check"],
            intents=["compare", "judge"],
            document_types=["contract", "policy"],
            extracted_inputs={},
        )
        query = build_retrieval_query(
            question,
            facts={},
            retrieval_fact_keys={"current_nav", "warning_threshold"},
        )
        self.assertEqual(query.fact_values, {})
        self.assertIn("current_nav", query.fact_keys)
        self.assertIn("warning_threshold", query.fact_keys)

    def test_build_rule_asset_index_contains_rule_fields(self) -> None:
        rule = load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")
        record = build_rule_asset_index([rule])[0]
        self.assertEqual(record.rule_id, "private_fund.nav_risk_warning.v1")
        self.assertIn("current_nav", record.required_input_keys)
        self.assertIn("净值", record.query_signals)
        self.assertIn("private_fund.nav_risk_warning.v1", record.support_terms)

    def test_hybrid_retrieval_prefers_fund_full_rule_for_fund_case(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        rules = [
            load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json"),
            load_rule(FIXTURE_DIR / "rule_atomic_contractual_warning_gate.json"),
        ]
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)
        matches = retrieve_hybrid_matches_from_rules(rules, query, min_signal_hits=1, top_k=8)
        self.assertEqual(matches[0].record.rule_id, "private_fund.nav_risk_warning.v1")
        self.assertTrue(matches[0].eligible_for_direct_match)
        self.assertFalse(matches[1].eligible_for_direct_match)
        self.assertTrue(matches[1].eligible_for_composition)

    def test_hybrid_retrieval_uses_fact_hits_to_break_ties(self) -> None:
        base_path = FIXTURE_DIR / "rule_private_fund_nav_warning.json"
        matching_rule = _clone_rule(
            base_path,
            rule_id="fund.matching.v1",
            required_inputs=["current_nav", "warning_threshold", "contract_requires_warning"],
            query_signals=["净值", "风险提示"],
        )
        sparse_rule = _clone_rule(
            base_path,
            rule_id="fund.sparse.v1",
            required_inputs=["threshold_breached", "warning_required"],
            query_signals=["净值", "风险提示"],
        )
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)
        matches = retrieve_hybrid_matches_from_rules([sparse_rule, matching_rule], query, min_signal_hits=1, top_k=8)
        self.assertEqual(matches[0].record.rule_id, "fund.matching.v1")
        self.assertGreater(matches[0].fact_hits, matches[1].fact_hits)

    def test_hybrid_retrieval_uses_signal_fact_keys_to_break_ties_without_runtime_facts(self) -> None:
        base_path = FIXTURE_DIR / "rule_private_fund_nav_warning.json"
        matching_rule = _clone_rule(
            base_path,
            rule_id="fund.signal_matching.v1",
            required_inputs=["current_nav", "warning_threshold", "contract_requires_warning"],
            query_signals=["净值", "风险提示"],
        )
        sparse_rule = _clone_rule(
            base_path,
            rule_id="fund.signal_sparse.v1",
            required_inputs=["threshold_breached", "warning_required"],
            query_signals=["净值", "风险提示"],
        )
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        query = build_retrieval_query(
            question,
            facts={},
            retrieval_fact_keys={"current_nav", "warning_threshold", "contract_requires_warning"},
        )
        matches = retrieve_hybrid_matches_from_rules([sparse_rule, matching_rule], query, min_signal_hits=1, top_k=8)
        self.assertEqual(matches[0].record.rule_id, "fund.signal_matching.v1")
        self.assertGreater(matches[0].fact_hits, matches[1].fact_hits)

    def test_semantic_rerank_can_keep_related_rule_eligible_when_signal_hits_low(self) -> None:
        question = QuestionStruct(
            question_text="某私募产品单位份额价格触发合同警戒线后，管理人是否要向持有人做提示？",
            question_types=["policy_check"],
            intents=["compare", "judge"],
            document_types=["contract", "policy"],
            extracted_inputs={},
        )
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        rules = [load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")]
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)
        matches = retrieve_hybrid_matches_from_rules(rules, query, min_signal_hits=1, top_k=8)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].signal_hits, 0)
        self.assertGreater(matches[0].score_breakdown["semantic"], 0)
        self.assertTrue(any(reason.startswith("semantic_gate_score=") for reason in matches[0].reasons))
        self.assertTrue(matches[0].eligible_for_direct_match)

    def test_semantic_rerank_does_not_flip_unrelated_credit_rule_for_fund_case(self) -> None:
        question = QuestionStruct(
            question_text="某私募产品单位份额价格触发合同警戒线后，管理人是否要向持有人做提示？",
            question_types=["policy_check"],
            intents=["compare", "judge"],
            document_types=["contract", "policy"],
            extracted_inputs={},
        )
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        rules = [load_rule(FIXTURE_DIR / "rule_credit_loan_extension_notice.json")]
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)
        matches = retrieve_hybrid_matches_from_rules(rules, query, min_signal_hits=1, top_k=8)
        self.assertEqual(len(matches), 1)
        self.assertFalse(matches[0].eligible_for_direct_match)


if __name__ == "__main__":
    unittest.main()
