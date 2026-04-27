from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.api import handle_request
from phase1_runtime.datasets import import_dataset_dir, run_full_workflow
from phase1_runtime.tools.mock_data_credit import generate_credit_simulation_dataset
from phase1_runtime.runtime_core import Phase1Runtime
from phase1_runtime.schema import load_document_bundle, load_question, load_rule


FIXTURE_DIR = Path("phase1_runtime/fixtures")


class Phase1CreditCaseTests(unittest.TestCase):
    def test_credit_runtime_direct_match(self) -> None:
        rule = load_rule(FIXTURE_DIR / "rule_credit_loan_extension_notice.json")
        question = load_question(FIXTURE_DIR / "question_credit_loan_extension_notice.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_credit_loan_extension_notice.json")

        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir)
            result = runtime.run(question, [rule], facts, evidence_refs)
            self.assertEqual(result.matched_rule_id, "credit.loan_extension_notice.v1")
            self.assertEqual(result.final_result["decision"], "must_notify")
            self.assertTrue(result.final_result["notice_required"])

    def test_credit_dataset_generation_and_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = generate_credit_simulation_dataset(tmpdir)
            self.assertTrue(summary["validation_valid"])
            self.assertEqual(summary["matched_rule_id"], "credit.loan_extension_notice.v1")

            imported = import_dataset_dir(tmpdir)
            self.assertEqual(imported.simulation_dataset.dataset_id, "demo_set_credit_001")
            self.assertEqual(imported.execution_trace.retrieval["matched_rule_id"], "credit.loan_extension_notice.v1")
            self.assertEqual(imported.execution_trace.final_result["decision"], "must_notify")

    def test_credit_workflow_and_api(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            dataset_dir = Path(tmpdir) / "credit_dataset"
            generate_credit_simulation_dataset(dataset_dir)

            workflow = run_full_workflow(dataset_dir=dataset_dir, trace_dir=Path(tmpdir) / "workflow_traces")
            self.assertEqual(workflow["import_summary"]["dataset_id"], "demo_set_credit_001")
            self.assertEqual(workflow["replay_summary"]["final_decision"], "must_notify")
            self.assertTrue(workflow["rerun_summary"]["all_consistent"])

            response = handle_request(
                {
                    "action": "workflow.full",
                    "dataset_dir": str(dataset_dir),
                    "request_id": "req_credit_001",
                }
            )
            self.assertTrue(response["ok"])
            self.assertEqual(response["data"]["import_summary"]["matched_rule_id"], "credit.loan_extension_notice.v1")
            self.assertEqual(response["data"]["replay_summary"]["final_decision"], "must_notify")


if __name__ == "__main__":
    unittest.main()
