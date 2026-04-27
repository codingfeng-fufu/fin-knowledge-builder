from __future__ import annotations

from pathlib import Path
import unittest

from phase1_runtime.runtime_core import build_composition_plan
from phase1_runtime.retrieval import retrieve_candidates, select_composable_candidates
from phase1_runtime.schema import load_document_bundle, load_question, load_rule


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


class CompilerCompositionTests(unittest.TestCase):
    def test_build_composition_plan_for_atomic_fund_rules(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, _ = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        rules = [load_rule(FIXTURE_DIR / filename) for filename in ATOMIC_RULE_FILES]

        candidates = retrieve_candidates(rules, question, min_signal_hits=1, top_k=8)
        composable_candidates = select_composable_candidates(candidates)
        plan = build_composition_plan(question, composable_candidates, facts)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["composition_pattern"], "derive_then_decide")
        self.assertEqual(plan["source_rule_ids"], [
            "atomic.numeric_threshold_breach.v1",
            "atomic.contractual_warning_gate.v1",
            "atomic.policy_answer_builder.v1",
        ])
        self.assertEqual([node["composition_role"] for node in plan["plan_dag"]], [
            "derive_value",
            "condition_check",
            "final_decision",
        ])


    def test_build_composition_plan_for_atomic_credit_rules(self) -> None:
        question = load_question(FIXTURE_DIR / "question_credit_loan_extension_notice.json")
        facts, _ = load_document_bundle(FIXTURE_DIR / "document_bundle_credit_loan_extension_notice.json")
        rules = [load_rule(FIXTURE_DIR / filename) for filename in CREDIT_ATOMIC_RULE_FILES]

        candidates = retrieve_candidates(rules, question, min_signal_hits=1, top_k=8)
        composable_candidates = select_composable_candidates(candidates)
        plan = build_composition_plan(question, composable_candidates, facts)

        self.assertIsNotNone(plan)
        self.assertEqual(plan["composition_pattern"], "derive_then_decide")
        self.assertEqual(plan["source_rule_ids"], [
            "atomic.notice_window_open.v1",
            "atomic.contractual_notice_gate.v1",
            "atomic.notice_answer_builder.v1",
        ])
        self.assertEqual([node["composition_role"] for node in plan["plan_dag"]], [
            "derive_value",
            "condition_check",
            "final_decision",
        ])

if __name__ == "__main__":
    unittest.main()
