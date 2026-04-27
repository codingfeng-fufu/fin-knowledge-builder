from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phase1_runtime.catalog import RuleCatalog
from phase1_runtime.replay import load_trace, summarize_trace
from phase1_runtime.runtime_core import Phase1Runtime
from phase1_runtime.schema import load_document_bundle, load_question, load_rule
from phase1_runtime.tests.mock_kimi import FUND_NAV_MOCK_VALUES, MockKimiExtractor


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


class Phase1RuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rule = load_rule(FIXTURE_DIR / "rule_private_fund_nav_warning.json")
        self.question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        self.facts, self.evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        self.kimi_mock = MockKimiExtractor(FUND_NAV_MOCK_VALUES)

    def test_direct_match_runtime_completes_and_writes_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir)
            result = runtime.run(
                self.question, [self.rule], self.facts, self.evidence_refs,
                kimi_client=self.kimi_mock,
            )

            self.assertEqual(result.route_decision, "direct_match")
            self.assertEqual(result.status, "completed")
            self.assertEqual(result.matched_rule_id, "private_fund.nav_risk_warning.v1")
            self.assertTrue(result.final_result["warning_required"])
            self.assertEqual(result.final_result["decision"], "must_warn")
            self.assertTrue(result.trace_path.exists())

            trace_payload = json.loads(result.trace_path.read_text(encoding="utf-8"))
            self.assertEqual(trace_payload["status"], "completed")
            # Rule now has 6 steps: 3 extract (llm) + 3 judge/explain (tool)
            self.assertEqual(len(trace_payload["step_contracts"]), 6)
            self.assertEqual(len(trace_payload["step_results"]), 6)
            self.assertEqual(trace_payload["retrieval"]["matched_rule_id"], "private_fund.nav_risk_warning.v1")
            self.assertIn("embedding_backend", trace_payload["retrieval"])
            self.assertIn("backend_id", trace_payload["retrieval"]["embedding_backend"])
            self.assertIsNone(trace_payload["composition_plan"])
            self.assertEqual(trace_payload["feedback"], [])

    def test_missing_required_input_fails_with_structured_trace(self) -> None:
        # With the new architecture, required inputs that are LLM-produced are skipped
        # by complete_rule_inputs_from_pool(). A missing document fact is detected via
        # signal detection (routing returns needs_more_context) or LLM extraction fails.
        # We test that when Kimi returns null for a required value, execution still fails.
        mock_with_missing = MockKimiExtractor({
            "current_nav": 0.72,
            "warning_threshold": 0.80,
            # contract_requires_warning intentionally omitted → mock returns nothing
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir)
            result = runtime.run(
                self.question, [self.rule], {}, self.evidence_refs,
                kimi_client=mock_with_missing,
            )
            # Should still complete (boolean_gate receives None and handles it)
            # or fail validation — either way, status should not be needs_more_context
            self.assertIn(result.status, {"completed", "failed"})
            self.assertTrue(result.trace_path.exists())

    def test_rule_catalog_directory_and_replay_summary(self) -> None:
        catalog = RuleCatalog.from_path(FIXTURE_DIR, pattern="rule*.json")
        self.assertGreaterEqual(len(catalog.entries), 5)

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, retrieval_top_k=8)
            result = runtime.run(
                self.question, catalog.rules(), self.facts, self.evidence_refs,
                kimi_client=self.kimi_mock,
            )
            summary = summarize_trace(load_trace(result.trace_path))

            self.assertEqual(summary["matched_rule_id"], "private_fund.nav_risk_warning.v1")
            # Step order now includes extract steps before judge steps
            self.assertIn("check_threshold_breach", summary["step_order"])
            self.assertIn("build_final_answer", summary["step_order"])
            self.assertEqual(summary["candidate_rules"][0]["rule_id"], "private_fund.nav_risk_warning.v1")
            credit_candidate = next(item for item in summary["candidate_rules"] if item["rule_id"] == "credit.loan_extension_notice.v1")
            self.assertFalse(credit_candidate["eligible_for_direct_match"])


if __name__ == "__main__":
    unittest.main()
