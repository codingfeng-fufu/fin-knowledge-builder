from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.datasets import (
    replay_imported_dataset,
    rerun_imported_dataset,
    summarize_imported_dataset,
)
from phase1_runtime.datasets import import_dataset_dir


DEMO_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")


class Phase1ConsumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.imported = import_dataset_dir(DEMO_DATASET_DIR)

    def test_summarize_imported_dataset(self) -> None:
        summary = summarize_imported_dataset(self.imported)
        self.assertEqual(summary["dataset_id"], "demo_set_001")
        self.assertEqual(summary["final_decision"], "must_warn")
        self.assertEqual(summary["document_count"], 2)

    def test_replay_imported_dataset(self) -> None:
        replay_summary = replay_imported_dataset(self.imported)
        self.assertEqual(replay_summary["matched_rule_id"], "private_fund.nav_risk_warning.v1")
        self.assertEqual(replay_summary["final_decision"], "must_warn")
        self.assertEqual(replay_summary["scenario_name"], "private_fund_nav_warning_v001")

    def test_rerun_imported_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rerun_summary = rerun_imported_dataset(self.imported, trace_dir=tmpdir)
            self.assertTrue(rerun_summary["all_consistent"])
            self.assertTrue(Path(rerun_summary["rerun_trace_path"]).exists())
            self.assertEqual(rerun_summary["rerun_matched_rule_id"], "private_fund.nav_risk_warning.v1")


if __name__ == "__main__":
    unittest.main()
