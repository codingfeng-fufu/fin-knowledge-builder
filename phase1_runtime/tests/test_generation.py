from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phase1_runtime.contracts import write_formal_schemas
from phase1_runtime.tools.mock_data import (
    DEFAULT_SCENARIO_VARIANTS,
    generate_batch_simulation_datasets,
    generate_simulation_dataset,
)


class Phase1GenerationTests(unittest.TestCase):
    def test_write_formal_schemas_outputs_registry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = write_formal_schemas(tmpdir)
            self.assertEqual(summary["schema_count"], 17)
            self.assertTrue(Path(summary["index_file"]).exists())
            index_payload = json.loads(Path(summary["index_file"]).read_text(encoding="utf-8"))
            self.assertEqual(index_payload["schema_count"], 17)
            self.assertIn("simulation_dataset", index_payload["schemas"])

    def test_generate_single_dataset_writes_validation_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            summary = generate_simulation_dataset(tmpdir, variant=DEFAULT_SCENARIO_VARIANTS[0])
            self.assertTrue(summary["validation_valid"])
            validation_summary = summary["validation"]
            self.assertTrue(validation_summary["valid"])
            self.assertEqual(validation_summary["validated_files"], 8)
            validation_path = Path(validation_summary["summary_file"])
            self.assertTrue(validation_path.exists())

    def test_generate_batch_simulation_datasets_outputs_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = generate_batch_simulation_datasets(tmpdir, variant_configs=DEFAULT_SCENARIO_VARIANTS[:3])
            self.assertEqual(manifest["dataset_count"], 3)
            self.assertEqual(manifest["status_counts"]["completed"], 3)
            self.assertTrue(Path(manifest["manifest_file"]).exists())
            dataset_dirs = [Path(item["output_dir"]) for item in manifest["datasets"]]
            self.assertEqual(len(dataset_dirs), 3)
            for dataset_dir in dataset_dirs:
                self.assertTrue((dataset_dir / "simulation_dataset.json").exists())
                self.assertTrue((dataset_dir / "generation_summary.json").exists())
                self.assertTrue((dataset_dir / "validation_summary.json").exists())


if __name__ == "__main__":
    unittest.main()
