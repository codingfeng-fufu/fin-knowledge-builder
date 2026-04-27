from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.prototype import list_prototype_flows, run_prototype_flow


class Phase1PrototypeServiceTests(unittest.TestCase):
    def test_list_prototype_flows(self) -> None:
        payload = list_prototype_flows()
        self.assertGreaterEqual(payload["flow_count"], 3)
        flow_ids = {item["flow_id"] for item in payload["flows"]}
        self.assertIn("fund_direct", flow_ids)
        self.assertIn("fund_compose", flow_ids)
        self.assertIn("credit_compose", flow_ids)

    def test_run_prototype_flow_credit_compose(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = run_prototype_flow("credit_compose", work_dir=tmpdir)
            self.assertEqual(payload["prototype_status"], "completed")
            self.assertEqual(payload["route_decision"], "rule_composable")
            self.assertEqual(payload["composition_pattern"], "derive_then_decide")
            self.assertEqual(payload["final_decision"], "must_notify")
            self.assertEqual(payload["solution_view"]["route"]["route_decision"], "rule_composable")
            self.assertGreaterEqual(payload["solution_view"]["retrieval"]["asset_counts"]["candidate_total"], 3)
            self.assertTrue(Path(payload["rerun_trace_path"]).exists())


if __name__ == "__main__":
    unittest.main()
