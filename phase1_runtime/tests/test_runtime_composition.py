from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phase1_runtime.runtime_core import Phase1Runtime
from phase1_runtime.schema import load_document_bundle, load_question, load_rule
from phase1_runtime.tests.mock_kimi import CREDIT_NOTICE_MOCK_VALUES, FUND_NAV_MOCK_VALUES, MockKimiExtractor


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"
ATOMIC_RULE_FILES = [
    "rule_atomic_numeric_threshold_breach.json",
    "rule_atomic_contractual_warning_gate.json",
    "rule_atomic_policy_answer_builder.json",
]
CREDIT_ATOMIC_RULE_FILES = [
    "rule_atomic_notice_window_open.json",
    "rule_atomic_contractual_notice_gate.json",
    "rule_atomic_notice_answer_builder.json",
]


class Phase1RuntimeCompositionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        self.facts, self.evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        self.atomic_rules = [load_rule(FIXTURE_DIR / filename) for filename in ATOMIC_RULE_FILES]
        self.credit_rule = load_rule(FIXTURE_DIR / "rule_credit_loan_extension_notice.json")
        self.credit_question = load_question(FIXTURE_DIR / "question_credit_loan_extension_notice.json")
        self.credit_facts, self.credit_evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_credit_loan_extension_notice.json")
        self.credit_atomic_rules = [load_rule(FIXTURE_DIR / filename) for filename in CREDIT_ATOMIC_RULE_FILES]

    def test_runtime_composes_atomic_rules_when_no_direct_match_exists(self) -> None:
        kimi_mock = MockKimiExtractor(FUND_NAV_MOCK_VALUES)
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, retrieval_top_k=8)
            result = runtime.run(
                self.question, self.atomic_rules, self.facts, self.evidence_refs,
                kimi_client=kimi_mock,
            )

            self.assertEqual(result.route_decision, "rule_composable")
            self.assertEqual(result.status, "completed")
            self.assertIsNone(result.matched_rule_id)
            self.assertEqual(result.composition_pattern, "derive_then_decide")
            self.assertEqual(result.source_rule_ids, [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])
            self.assertEqual(result.final_result["decision"], "must_warn")

            trace = json.loads(result.trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace["route_decision"], "rule_composable")
            self.assertEqual(trace["composition_plan"]["composition_pattern"], "derive_then_decide")
            self.assertEqual(len(trace["composition_trace"]["rule_results"]), 3)
            self.assertEqual(trace["composition_trace"]["final_decision"], "must_warn")
            # Rules now have LLM extract steps: 3+2+2 = 7 steps across 3 atomic rules
            self.assertGreaterEqual(len(trace["step_contracts"]), 3)
            self.assertTrue(all(contract["composition_plan_id"] for contract in trace["step_contracts"]))

    def test_runtime_composes_credit_atomic_rules_when_no_direct_match_exists(self) -> None:
        kimi_mock = MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES)
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, retrieval_top_k=8)
            result = runtime.run(
                self.credit_question, self.credit_atomic_rules, self.credit_facts, self.credit_evidence_refs,
                kimi_client=kimi_mock,
            )

            self.assertEqual(result.route_decision, "rule_composable")
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.composition_pattern, "derive_then_decide")
            self.assertEqual(result.source_rule_ids, [
                "atomic.notice_window_open.v1",
                "atomic.contractual_notice_gate.v1",
                "atomic.notice_answer_builder.v1",
            ])
            self.assertEqual(result.final_result["decision"], "must_notify")
            self.assertTrue(result.final_result["notice_required"])

            trace = json.loads(result.trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace["composition_trace"]["final_decision"], "must_notify")

    def test_runtime_falls_back_to_exploration_when_no_direct_or_composable_rule_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir)
            result = runtime.run(self.question, [self.credit_rule], self.facts, self.evidence_refs)

            self.assertEqual(result.route_decision, "exploration")
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.failure_reason, "no_direct_or_composable_rule")

            trace = json.loads(result.trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace["feedback"][0]["feedback_type"], "missed_rule")
            self.assertIsNone(trace["composition_plan"])
            self.assertEqual(trace["step_contracts"], [])


if __name__ == "__main__":
    unittest.main()
