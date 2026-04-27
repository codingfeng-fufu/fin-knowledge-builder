from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from phase1_runtime.registry import (
    get_registered_dataset,
    get_workflow_run,
    list_registered_datasets,
    list_workflow_runs,
    register_dataset,
    run_registered_workflow_sync,
    submit_registered_workflow,
)


FUND_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
CREDIT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_credit_001")


class Phase1RegistryTests(unittest.TestCase):
    def test_register_and_list_datasets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            register_dataset(FUND_DATASET_DIR, db_path=db_path)
            register_dataset(CREDIT_DATASET_DIR, db_path=db_path)

            listing = list_registered_datasets(db_path=db_path)
            self.assertEqual(listing["dataset_count"], 2)
            dataset_ids = [item["dataset_id"] for item in listing["datasets"]]
            self.assertEqual(dataset_ids, ["demo_set_001", "demo_set_credit_001"])

            credit = get_registered_dataset("demo_set_credit_001", db_path=db_path)
            self.assertEqual(credit["summary"]["matched_rule_id"], "credit.loan_extension_notice.v1")
            self.assertTrue(credit["validation_valid"])

    def test_run_and_list_workflow_registry_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            trace_dir = Path(tmpdir) / "workflow_traces"
            register_dataset(FUND_DATASET_DIR, db_path=db_path)

            run_record = run_registered_workflow_sync(
                dataset_id="demo_set_001",
                request_id="reg_run_001",
                trace_dir=trace_dir,
                db_path=db_path,
            )
            self.assertEqual(run_record["status"], "completed")
            self.assertEqual(run_record["final_decision"], "must_warn")

            fetched = get_workflow_run(run_record["run_id"], db_path=db_path)
            self.assertEqual(fetched["request_id"], "reg_run_001")

            listing = list_workflow_runs(db_path=db_path)
            self.assertEqual(listing["run_count"], 1)
            self.assertEqual(listing["runs"][0]["dataset_id"], "demo_set_001")

    def test_submit_workflow_registry_async(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            trace_dir = Path(tmpdir) / "workflow_traces"
            register_dataset(FUND_DATASET_DIR, db_path=db_path)

            run_record = submit_registered_workflow(
                dataset_id="demo_set_001",
                request_id="reg_async_001",
                trace_dir=trace_dir,
                db_path=db_path,
            )
            self.assertEqual(run_record["status"], "queued")

            deadline = time.time() + 30
            latest = run_record
            while time.time() < deadline:
                latest = get_workflow_run(run_record["run_id"], db_path=db_path)
                if latest["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)

            self.assertEqual(latest["status"], "completed")
            self.assertEqual(latest["final_decision"], "must_warn")


if __name__ == "__main__":
    unittest.main()
