from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from phase1_runtime.datasets import run_full_workflow
from phase1_runtime.factory import (
    approve_review,
    create_review_for_draft,
    generate_candidate_rule_draft,
    ingest_case_from_dataset,
)
from phase1_runtime.runtime_core import Phase1Runtime
from phase1_runtime.schema import load_document_bundle, load_question, load_rule


DEMO_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
CREDIT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_credit_001")
CREDIT_RULE_FIXTURE = Path("phase1_runtime/fixtures/rule_credit_loan_extension_notice.json")
ATOMIC_RULE_FIXTURES = [
    Path("phase1_runtime/fixtures/rule_atomic_numeric_threshold_breach.json"),
    Path("phase1_runtime/fixtures/rule_atomic_contractual_warning_gate.json"),
    Path("phase1_runtime/fixtures/rule_atomic_policy_answer_builder.json"),
]
CREDIT_ATOMIC_RULE_FIXTURES = [
    Path("phase1_runtime/fixtures/rule_atomic_notice_window_open.json"),
    Path("phase1_runtime/fixtures/rule_atomic_contractual_notice_gate.json"),
    Path("phase1_runtime/fixtures/rule_atomic_notice_answer_builder.json"),
]


def _build_dataset_without_fund_rule(root: Path) -> Path:
    dataset_dir = root / "missing_fund_rule_dataset"
    shutil.copytree(DEMO_DATASET_DIR, dataset_dir)
    credit_rule = json.loads(CREDIT_RULE_FIXTURE.read_text(encoding="utf-8"))
    (dataset_dir / "rule_pool.json").write_text(
        json.dumps([credit_rule], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    simulation_dataset = json.loads((dataset_dir / "simulation_dataset.json").read_text(encoding="utf-8"))
    simulation_dataset["rule_pool"] = [credit_rule]
    (dataset_dir / "simulation_dataset.json").write_text(
        json.dumps(simulation_dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dataset_dir


def _build_dataset_with_atomic_rules(root: Path, source_dataset_dir: Path, fixture_paths: list[Path], target_name: str) -> Path:
    dataset_dir = root / target_name
    shutil.copytree(source_dataset_dir, dataset_dir)
    atomic_rules = [json.loads(path.read_text(encoding="utf-8")) for path in fixture_paths]
    atomic_rule_objects = [load_rule(path) for path in fixture_paths]
    (dataset_dir / "rule_pool.json").write_text(
        json.dumps(atomic_rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    question = load_question(dataset_dir / "question_struct.json")
    facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
    runtime = Phase1Runtime(trace_dir=root / "seed_traces", retrieval_top_k=8)
    seeded_result = runtime.run(
        question=question,
        rules=atomic_rule_objects,
        facts=facts,
        evidence_refs=evidence_refs,
    )
    seeded_trace = json.loads(seeded_result.trace_path.read_text(encoding="utf-8"))
    (dataset_dir / "execution_trace.json").write_text(
        json.dumps(seeded_trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    simulation_dataset = json.loads((dataset_dir / "simulation_dataset.json").read_text(encoding="utf-8"))
    simulation_dataset["rule_pool"] = atomic_rules
    simulation_dataset["execution_trace"] = seeded_trace
    (dataset_dir / "simulation_dataset.json").write_text(
        json.dumps(simulation_dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dataset_dir


class Phase1WorkflowTests(unittest.TestCase):
    def test_run_full_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_full_workflow(dataset_dir=DEMO_DATASET_DIR, trace_dir=tmpdir)
            self.assertEqual(payload["workflow_status"], "completed")
            self.assertTrue(payload["validation"]["valid"])
            self.assertEqual(payload["import_summary"]["dataset_id"], "demo_set_001")
            self.assertEqual(payload["replay_summary"]["final_decision"], "must_warn")
            self.assertTrue(payload["rerun_summary"]["all_consistent"])
            self.assertTrue(Path(payload["rerun_summary"]["rerun_trace_path"]).exists())

    def test_run_full_workflow_with_atomic_rule_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            dataset_dir = _build_dataset_with_atomic_rules(tmp_root, DEMO_DATASET_DIR, ATOMIC_RULE_FIXTURES, "atomic_fund_dataset")
            payload = run_full_workflow(dataset_dir=dataset_dir, trace_dir=tmp_root / "workflow_traces")

            self.assertEqual(payload["workflow_status"], "completed")
            self.assertTrue(payload["validation"]["valid"])
            self.assertEqual(payload["rerun_summary"]["rerun_status"], "completed")
            self.assertEqual(payload["rerun_summary"]["rerun_route_decision"], "rule_composable")
            self.assertEqual(payload["rerun_summary"]["rerun_composition_pattern"], "derive_then_decide")
            self.assertEqual(payload["rerun_summary"]["rerun_source_rule_ids"], [
                "atomic.numeric_threshold_breach.v1",
                "atomic.contractual_warning_gate.v1",
                "atomic.policy_answer_builder.v1",
            ])
            self.assertTrue(payload["rerun_summary"]["all_consistent"])

    def test_run_full_workflow_with_credit_atomic_rule_composition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            dataset_dir = _build_dataset_with_atomic_rules(
                tmp_root,
                CREDIT_DATASET_DIR,
                CREDIT_ATOMIC_RULE_FIXTURES,
                "atomic_credit_dataset",
            )
            payload = run_full_workflow(dataset_dir=dataset_dir, trace_dir=tmp_root / "workflow_traces")

            self.assertEqual(payload["workflow_status"], "completed")
            self.assertTrue(payload["validation"]["valid"])
            self.assertEqual(payload["rerun_summary"]["rerun_status"], "completed")
            self.assertEqual(payload["rerun_summary"]["rerun_route_decision"], "rule_composable")
            self.assertEqual(payload["rerun_summary"]["rerun_composition_pattern"], "derive_then_decide")
            self.assertEqual(payload["rerun_summary"]["rerun_source_rule_ids"], [
                "atomic.notice_window_open.v1",
                "atomic.contractual_notice_gate.v1",
                "atomic.notice_answer_builder.v1",
            ])
            self.assertTrue(payload["rerun_summary"]["all_consistent"])

    def test_run_full_workflow_reuses_published_rules_from_factory_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_root = Path(tmpdir)
            dataset_dir = _build_dataset_without_fund_rule(tmp_root)
            db_path = tmp_root / "registry.db"
            trace_dir = tmp_root / "workflow_traces"

            payload_without_publish = run_full_workflow(
                dataset_dir=dataset_dir,
                trace_dir=trace_dir,
                db_path=db_path,
            )
            self.assertEqual(payload_without_publish["rerun_summary"]["rerun_status"], "failed")
            self.assertEqual(payload_without_publish["rerun_summary"]["rerun_route_decision"], "exploration")
            self.assertIsNone(payload_without_publish["rerun_summary"]["rerun_matched_rule_id"])

            case = ingest_case_from_dataset(DEMO_DATASET_DIR, db_path=db_path)
            draft = generate_candidate_rule_draft(case["case_id"], db_path=db_path)
            review = create_review_for_draft(draft["draft_id"], db_path=db_path)
            approve_review(review["review_task_id"], db_path=db_path)

            payload_with_publish = run_full_workflow(
                dataset_dir=dataset_dir,
                trace_dir=trace_dir,
                db_path=db_path,
            )
            self.assertEqual(payload_with_publish["rerun_summary"]["rerun_status"], "completed")
            self.assertEqual(
                payload_with_publish["rerun_summary"]["rerun_matched_rule_id"],
                "private_fund.nav_risk_warning.v1",
            )
            self.assertTrue(payload_with_publish["rerun_summary"]["all_consistent"])
            self.assertGreaterEqual(payload_with_publish["rerun_summary"]["runtime_rule_count"], 2)


if __name__ == "__main__":
    unittest.main()
