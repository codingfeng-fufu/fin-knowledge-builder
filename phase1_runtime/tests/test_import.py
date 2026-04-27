from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from phase1_runtime.datasets import DatasetImportError, import_dataset_dir


DEMO_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")


class Phase1ImportTests(unittest.TestCase):
    def test_import_dataset_dir_loads_valid_dataset(self) -> None:
        imported = import_dataset_dir(DEMO_DATASET_DIR)

        self.assertEqual(imported.simulation_dataset.dataset_id, "demo_set_001")
        self.assertEqual(imported.question.question_text, "某私募产品净值跌破0.80后，是否需要向投资者做风险提示？")
        self.assertEqual(len(imported.rule_pool), 2)
        self.assertEqual(imported.execution_trace.retrieval["matched_rule_id"], "private_fund.nav_risk_warning.v1")
        self.assertTrue(imported.validation_summary["valid"])

    def test_import_dataset_dir_rejects_invalid_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            broken_dir = Path(tmpdir) / "broken_dataset"
            shutil.copytree(DEMO_DATASET_DIR, broken_dir)

            question_path = broken_dir / "question_struct.json"
            payload = json.loads(question_path.read_text(encoding="utf-8"))
            payload.pop("question_text")
            question_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            with self.assertRaises(DatasetImportError):
                import_dataset_dir(broken_dir)


if __name__ == "__main__":
    unittest.main()
