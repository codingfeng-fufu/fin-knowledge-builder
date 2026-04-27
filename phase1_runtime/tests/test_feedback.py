from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from phase1_runtime.factory import (
    get_feedback_service,
    list_feedback_service,
    record_feedback,
)


class Phase1FeedbackTests(unittest.TestCase):
    def test_record_and_list_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            recorded = record_feedback(
                trace_id="trace_demo_001",
                route_decision="exploration",
                feedback_type="missed_rule",
                rule_ids=["credit.loan_extension_notice.v1"],
                payload={"reason": "no_direct_or_composable_rule"},
                case_id="case_credit_loan_extension_notice_001",
                db_path=db_path,
            )

            self.assertEqual(recorded["trace_id"], "trace_demo_001")
            self.assertEqual(recorded["feedback_type"], "missed_rule")
            self.assertEqual(recorded["rule_ids"], ["credit.loan_extension_notice.v1"])
            self.assertEqual(recorded["payload"]["classification"], "coverage_gap")
            self.assertEqual(recorded["payload"]["recommended_action"], "create_new_atomic_rule")
            self.assertEqual(recorded["payload"]["source_payload"]["reason"], "no_direct_or_composable_rule")

            fetched = get_feedback_service(recorded["feedback_id"], db_path=db_path)
            self.assertEqual(fetched["feedback_id"], recorded["feedback_id"])
            self.assertEqual(fetched["payload"]["classification"], "coverage_gap")
            self.assertEqual(fetched["payload"]["recommended_action"], "create_new_atomic_rule")
            self.assertEqual(fetched["payload"]["source_payload"]["reason"], "no_direct_or_composable_rule")

            listing = list_feedback_service(db_path=db_path)
            self.assertEqual(listing["feedback_count"], 1)
            self.assertEqual(listing["feedback"][0]["feedback_id"], recorded["feedback_id"])


if __name__ == "__main__":
    unittest.main()
