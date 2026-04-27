from __future__ import annotations

from pathlib import Path
import unittest

from phase1_runtime.runtime_core import bind_rule, bind_rules_from_trace
from phase1_runtime.schema import load_document_bundle, load_question, load_rule
from phase1_runtime.runtime_core import build_task_context


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class RuleBindingTests(unittest.TestCase):
    def test_build_task_context_marks_grounded_and_assumed(self) -> None:
        task_context = build_task_context(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            scenario_hint="fund_nav_warning",
            parser_status="parsed_with_defaults",
            documents=[
                {"doc_id": "upload_doc_001", "title": "fund_clause.docx", "doc_type": "contract", "parse_status": "parsed_docx_text", "source_type": "uploaded_docx"},
            ],
            fact_sheet=[
                {"fact_id": "current_nav", "fact_type": "float", "value": 0.72, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "warning_threshold", "fact_type": "float", "value": 0.8, "source": "scenario_default", "evidence_refs": []},
            ],
            evidence_packets=[],
            unresolved_slots=["warning_threshold"],
        )
        self.assertEqual(task_context.context_status, "partially_grounded")
        self.assertEqual(task_context.fact_entries[0].status, "grounded")
        self.assertEqual(task_context.fact_entries[1].status, "assumed")

    def test_bind_rule_uses_context_fact_status(self) -> None:
        rule = load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")
        task_context = build_task_context(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            scenario_hint="fund_nav_warning",
            parser_status="parsed_with_defaults",
            documents=[],
            fact_sheet=[
                {"fact_id": "current_nav", "fact_type": "float", "value": 0.72, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "warning_threshold", "fact_type": "float", "value": 0.8, "source": "scenario_default", "evidence_refs": []},
            ],
            evidence_packets=[],
            unresolved_slots=["contract_requires_warning"],
        )
        binding = bind_rule(
            rule,
            task_context,
            retrieval_score=42,
            retrieval_reasons=["question_type_match", "intent_match"],
            eligible_for_direct_match=True,
        )
        self.assertEqual(binding.binding_status, "partially_bindable")
        self.assertIn("current_nav", binding.satisfied_slots)
        self.assertIn("warning_threshold", binding.assumed_slots)
        self.assertIn("contract_requires_warning", binding.missing_slots)

    def test_bind_rules_from_trace_uses_candidate_payloads(self) -> None:
        rule = load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")
        task_context = build_task_context(
            question_text="某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
            scenario_hint="fund_nav_warning",
            parser_status="parsed_complete",
            documents=[],
            fact_sheet=[
                {"fact_id": "current_nav", "fact_type": "float", "value": 0.72, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "warning_threshold", "fact_type": "float", "value": 0.8, "source": "parsed_upload", "evidence_refs": []},
                {"fact_id": "contract_requires_warning", "fact_type": "bool", "value": True, "source": "parsed_upload", "evidence_refs": []},
            ],
            evidence_packets=[],
        )
        bindings = bind_rules_from_trace(
            task_context=task_context,
            rule_by_id={rule.rule_id: rule},
            candidate_payloads=[
                {
                    "rule_id": rule.rule_id,
                    "score": 61,
                    "reasons": ["question_type_match"],
                    "eligible_for_direct_match": True,
                    "eligible_for_composition": False,
                }
            ],
        )
        self.assertEqual(len(bindings), 1)
        self.assertEqual(bindings[0].rule_id, rule.rule_id)
        self.assertEqual(bindings[0].binding_status, "bindable")
        self.assertEqual(bindings[0].retrieval_score, 61)


if __name__ == "__main__":
    unittest.main()
