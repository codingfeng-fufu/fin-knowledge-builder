from __future__ import annotations

import unittest

from phase1_runtime.analysis import run_exploration_runtime


class ExplorationRuntimeTests(unittest.TestCase):
    def test_builds_case_and_atomic_draft_for_exploration_gap(self) -> None:
        payload = run_exploration_runtime(
            scenario_id='fund_nav_warning',
            question_text='请给出处理意见。',
            route_decision='exploration',
            runtime_status='failed',
            final_decision='needs_review',
            failure_reason='no_direct_or_composable_rule',
            parser_status='defaults_only',
            missing_fact_keys=['current_nav', 'warning_threshold', 'contract_requires_warning'],
            fact_sheet=[],
            documents=[],
            matched_rule_id=None,
            source_rule_ids=[],
            fallback_rule_ids=['private_fund.nav_risk_warning.v1'],
        )
        self.assertEqual(payload['route_entry'], 'exploration')
        self.assertEqual(payload['trigger_reason'], 'no_direct_or_composable_rule')
        self.assertEqual(payload['case_draft']['scenario_id'], 'fund_nav_warning')
        self.assertEqual(payload['candidate_rule_drafts'][0]['draft_type'], 'candidate_atomic_rule_draft')
        self.assertEqual(payload['recommended_feedback_type'], 'missed_rule')

    def test_builds_composite_draft_for_failed_composition(self) -> None:
        payload = run_exploration_runtime(
            scenario_id='fund_nav_warning',
            question_text='基金净值跌破0.80后是否需要提示风险？',
            route_decision='rule_composable',
            runtime_status='failed',
            final_decision='needs_review',
            failure_reason='composition_failed',
            parser_status='parsed_complete',
            missing_fact_keys=[],
            fact_sheet=[{'fact_id': 'current_nav', 'value': 0.72}],
            documents=[{'doc_id': 'upload_doc_001'}],
            matched_rule_id=None,
            source_rule_ids=['atomic.numeric_threshold_breach.v1', 'atomic.contractual_warning_gate.v1'],
            fallback_rule_ids=['private_fund.nav_risk_warning.v1'],
        )
        self.assertEqual(payload['route_entry'], 'rule_composable')
        self.assertEqual(payload['candidate_rule_drafts'][0]['draft_type'], 'candidate_composite_rule_draft')
        self.assertEqual(payload['recommended_feedback_type'], 'composition_failure')
        self.assertGreaterEqual(len(payload['validator_pattern_suggestions']), 1)
