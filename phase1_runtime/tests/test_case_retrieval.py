"""Tests for M4 case-based retrieval."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase1_runtime.retrieval.case_retrieval import (
    CaseMatch,
    _bm25,
    _tok,
    retrieve_similar_cases,
    should_shortcut,
)
from phase1_runtime.factory.rule_factory_store import (
    ensure_rule_factory_db,
    insert_workspace_run_record,
)


def _seed_run(db_path: Path, wid: str, scenario: str, question: str, decision: str) -> None:
    """Insert a completed workspace run record for testing."""
    ensure_rule_factory_db(db_path=db_path)
    insert_workspace_run_record(
        workspace_run_id=wid,
        trace_id=f"trace_{wid}",
        case_id=f"case_{wid}",
        scenario_id=scenario,
        question_text=question,
        route_decision="direct_match",
        final_decision=decision,
        status="completed",
        payload={},
        db_path=db_path,
    )


class CaseRetrievalUnitTests(unittest.TestCase):

    def test_tokenize_mixed(self):
        tokens = _tok("净值0.72 NAV warning")
        self.assertIn("净值", tokens)
        self.assertIn("nav", tokens)
        self.assertIn("warning", tokens)

    def test_bm25_scores_relevant_higher(self):
        query = _tok("净值预警阈值")
        rel = _tok("当前基金净值低于预警阈值，需要触发警戒机制")
        irr = _tok("借款到期时间已过，请联系借款人")
        avg = (len(rel) + len(irr)) / 2
        self.assertGreater(_bm25(query, rel, avg), _bm25(query, irr, avg))

    def test_retrieve_empty_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            ensure_rule_factory_db(db_path=db)
            results = retrieve_similar_cases("净值是否达到预警线？", "fund_nav_warning", db_path=db)
            self.assertEqual(results, [])

    def test_retrieve_finds_similar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            _seed_run(db, "run_001", "fund_nav_warning",
                      "基金净值是否低于预警阈值？", "must_warn")
            _seed_run(db, "run_002", "fund_nav_warning",
                      "当前净值跌破警戒线了吗？", "must_warn")
            _seed_run(db, "run_003", "credit_notice",  # different scenario
                      "借款到期需要通知吗？", "must_notify")

            results = retrieve_similar_cases(
                "基金净值是否低于预警阈值？", "fund_nav_warning", db_path=db
            )
            self.assertGreater(len(results), 0)
            # All results should be fund_nav_warning
            for r in results:
                self.assertEqual(r.scenario_id, "fund_nav_warning")

    def test_retrieve_top_k_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            for i in range(10):
                _seed_run(db, f"run_{i:03d}", "fund_nav_warning",
                          f"净值预警检查 {i}", "must_warn")
            results = retrieve_similar_cases(
                "净值预警", "fund_nav_warning", db_path=db, top_k=3
            )
            self.assertLessEqual(len(results), 3)

    def test_retrieve_ordered_by_score(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = Path(tmpdir) / "test.db"
            _seed_run(db, "run_a", "fund_nav_warning",
                      "基金净值低于预警阈值警戒线", "must_warn")
            _seed_run(db, "run_b", "fund_nav_warning",
                      "完全无关的内容", "no_action")
            results = retrieve_similar_cases(
                "净值是否低于预警阈值", "fund_nav_warning", db_path=db
            )
            if len(results) >= 2:
                self.assertGreaterEqual(results[0].score, results[1].score)

    def test_should_shortcut_high_score(self):
        match = CaseMatch(
            workspace_run_id="x", case_id=None, scenario_id="s",
            question_text="q", final_decision="must_warn",
            route_decision="direct_match", score=0.95, created_at="",
        )
        self.assertIsNotNone(should_shortcut([match]))

    def test_should_shortcut_low_score(self):
        match = CaseMatch(
            workspace_run_id="x", case_id=None, scenario_id="s",
            question_text="q", final_decision="must_warn",
            route_decision="direct_match", score=0.3, created_at="",
        )
        self.assertIsNone(should_shortcut([match]))

    def test_should_shortcut_no_decision(self):
        match = CaseMatch(
            workspace_run_id="x", case_id=None, scenario_id="s",
            question_text="q", final_decision=None,
            route_decision="exploration", score=0.95, created_at="",
        )
        self.assertIsNone(should_shortcut([match]))

    def test_should_shortcut_empty(self):
        self.assertIsNone(should_shortcut([]))


class CaseRetrievalIntegrationTest(unittest.TestCase):
    """Verify similar_cases field appears in solve_workspace_request output."""

    def test_similar_cases_in_payload(self):
        from phase1_runtime.tests.mock_kimi import CREDIT_NOTICE_MOCK_VALUES, MockKimiExtractor
        from phase1_runtime.product import solve_workspace_request

        with tempfile.TemporaryDirectory() as tmpdir:
            payload = solve_workspace_request(
                question_text="是否需要发送借款人通知？",
                materials=[{"name": "notice.txt",
                            "content": "合同约定到期前5日内应通知借款人办理展期手续。"}],
                work_dir=tmpdir,
                kimi_client=MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES),
            )
            self.assertIn("similar_cases", payload)
            self.assertIsInstance(payload["similar_cases"], list)
            self.assertIn("shortcut_case", payload)

    def test_uploaded_materials_disable_shortcut_even_when_similar_case_exists(self):
        """Fresh uploads must execute normally instead of reusing a cached decision."""
        from phase1_runtime.tests.mock_kimi import CREDIT_NOTICE_MOCK_VALUES, MockKimiExtractor
        from phase1_runtime.product import solve_workspace_request

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "registry.db"
            mock = MockKimiExtractor(CREDIT_NOTICE_MOCK_VALUES)

            # First call: runs normally, stores result
            payload1 = solve_workspace_request(
                question_text="借款距到期20天，合同约定前30天通知，是否需要发送通知？",
                materials=[{"name": "notice.txt",
                            "content": "贷款到期前30日内应通知借款人。剩余20天。"}],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=mock,
            )
            self.assertIsNone(payload1["shortcut_case"])  # no prior cases

            # Second call: identical question still must not shortcut because
            # the request includes uploaded materials that need fresh handling.
            payload2 = solve_workspace_request(
                question_text="借款距到期20天，合同约定前30天通知，是否需要发送通知？",
                materials=[{"name": "notice.txt",
                            "content": "贷款到期前30日内应通知借款人。剩余20天。"}],
                work_dir=tmpdir,
                db_path=db_path,
                kimi_client=mock,
            )
            self.assertGreaterEqual(len(payload2["similar_cases"]), 1)
            self.assertIsNone(payload2.get("shortcut_case"))
            self.assertFalse(payload2["trace_id"].startswith("shortcut_"))
            self.assertIsNotNone(payload2["final_decision"])


if __name__ == "__main__":
    unittest.main()
