from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from phase1_runtime.retrieval import (
    build_retrieval_query,
    build_rule_graph_index,
    dense_retrieval_available,
    load_or_build_rule_graph_artifacts,
    load_persisted_rule_graph_artifacts,
    materialize_rule_graph_artifacts,
    retrieve_candidates,
    retrieve_dense_candidates,
    retrieve_rule_graph_rag,
    rewrite_retrieval_query,
    route_query_to_rule_graph,
)
from phase1_runtime.retrieval.rule_graph import nx
from phase1_runtime.schema import Rule, load_document_bundle, load_question


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def _clone_rule(
    path: Path,
    *,
    rule_id: str,
    rule_family: str,
) -> Rule:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rule_id"] = rule_id
    payload["name"] = f"cloned::{rule_id}"
    payload["rule_family"] = rule_family
    return Rule.from_dict(payload)


@unittest.skipIf(nx is None, "networkx not available")
class RuleGraphRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fund_full_rule = _clone_rule(
            FIXTURE_DIR / "rule_private_fund_nav_warning.json",
            rule_id="fund.full.v1",
            rule_family="private_fund_nav_warning",
        )
        self.fund_atomic_rule = _clone_rule(
            FIXTURE_DIR / "rule_atomic_contractual_warning_gate.json",
            rule_id="fund.atomic_gate.v1",
            rule_family="private_fund_nav_warning",
        )
        self.credit_full_rule = _clone_rule(
            FIXTURE_DIR / "rule_credit_loan_extension_notice.json",
            rule_id="credit.full.v1",
            rule_family="credit_loan_extension_notice",
        )
        self.credit_atomic_rule = _clone_rule(
            FIXTURE_DIR / "rule_atomic_contractual_notice_gate.json",
            rule_id="credit.atomic_gate.v1",
            rule_family="credit_loan_extension_notice",
        )
        self.rules = [
            self.fund_full_rule,
            self.fund_atomic_rule,
            self.credit_full_rule,
            self.credit_atomic_rule,
        ]

    def test_build_rule_graph_index_groups_related_rules_into_communities(self) -> None:
        index = build_rule_graph_index(self.rules)
        self.assertEqual(len(index.root_communities), 1)
        self.assertEqual(len(index.leaf_communities), 2)
        fund_community_id = index.community_by_rule_id[self.fund_full_rule.rule_id]
        self.assertEqual(fund_community_id, index.community_by_rule_id[self.fund_atomic_rule.rule_id])
        credit_community_id = index.community_by_rule_id[self.credit_full_rule.rule_id]
        self.assertEqual(credit_community_id, index.community_by_rule_id[self.credit_atomic_rule.rule_id])
        self.assertNotEqual(fund_community_id, credit_community_id)

        fund_community = next(community for community in index.communities if community.community_id == fund_community_id)
        self.assertEqual(fund_community.level, 1)
        self.assertIsNotNone(fund_community.parent_community_id)
        self.assertEqual(fund_community.meta_rule.dominant_rule_family, "private_fund_nav_warning")
        self.assertIn(self.fund_full_rule.rule_id, fund_community.meta_rule.rule_ids)
        self.assertIn("current_nav", fund_community.meta_rule.required_input_keys)
        self.assertTrue(fund_community.report.title)
        self.assertTrue(fund_community.report.findings)

    def test_route_query_to_rule_graph_prefers_matching_meta_rule_community(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)

        index = build_rule_graph_index(self.rules)
        route = route_query_to_rule_graph(index, query, top_k=1)

        self.assertFalse(route.used_fallback)
        self.assertIn(self.fund_full_rule.rule_id, route.candidate_rule_ids)
        self.assertIn(self.fund_atomic_rule.rule_id, route.candidate_rule_ids)
        self.assertNotIn(self.credit_full_rule.rule_id, route.candidate_rule_ids)
        self.assertNotIn(self.credit_atomic_rule.rule_id, route.candidate_rule_ids)
        self.assertTrue(route.selected_meta_rule_ids)
        self.assertEqual(len(route.selected_community_ids), 1)

    def test_query_rewrite_produces_multiple_structured_rewrites(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)

        rewrites = rewrite_retrieval_query(query)

        self.assertGreaterEqual(len(rewrites), 3)
        self.assertEqual(rewrites[0].strategy, "original_question")
        self.assertTrue(any(item.strategy == "facts_and_evidence" for item in rewrites))

    def test_retrieve_rule_graph_rag_returns_matching_community_report_and_rule_passages(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)

        index = build_rule_graph_index(self.rules)
        route = route_query_to_rule_graph(index, query, top_k=1)
        rag = retrieve_rule_graph_rag(index, query, route=route, top_k=6)

        self.assertTrue(any(item.passage_type == "community_report" for item in rag.passages))
        self.assertTrue(any(item.rule_id == self.fund_full_rule.rule_id for item in rag.passages))
        self.assertTrue(any(item.metadata.get("community_level") == 0 for item in rag.passages if item.passage_type == "community_report"))
        self.assertTrue(any(item.metadata.get("community_level") == 1 for item in rag.passages if item.passage_type == "community_report"))
        self.assertIn(self.fund_full_rule.rule_id, rag.metadata_by_rule_id)
        self.assertNotIn(self.credit_full_rule.rule_id, rag.metadata_by_rule_id)

    @unittest.skipUnless(dense_retrieval_available(), "dense retrieval stack not available")
    def test_retrieve_dense_candidates_returns_related_rule(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")
        query = build_retrieval_query(question, facts=facts, evidence_refs=evidence_refs)

        with tempfile.TemporaryDirectory() as tmpdir:
            index, rag_catalog, metadata = load_or_build_rule_graph_artifacts(self.rules, output_dir=tmpdir)
            dense = retrieve_dense_candidates(
                artifact_root=metadata["artifact_root"],
                passages=rag_catalog,
                query=query,
                top_k=8,
            )

            self.assertTrue(dense.candidates)
            self.assertEqual(dense.candidates[0].rule_id, self.fund_full_rule.rule_id)
            self.assertIn(self.fund_full_rule.rule_id, dense.metadata_by_rule_id)

    def test_rule_graph_artifacts_can_be_materialized_and_reloaded(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            materialized = materialize_rule_graph_artifacts(self.rules, output_dir=tmpdir)
            self.assertTrue(Path(materialized["artifact_root"]).exists())

            loaded = load_persisted_rule_graph_artifacts(self.rules, output_dir=tmpdir)
            self.assertIsNotNone(loaded)
            assert loaded is not None
            index, rag_catalog, metadata = loaded
            self.assertEqual(metadata["fingerprint"], materialized["fingerprint"])
            self.assertEqual(len(index.communities), 3)
            self.assertTrue(any(item.passage_type == "community_report" for item in rag_catalog))

    def test_load_or_build_rule_graph_artifacts_reports_cache_hit_on_second_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            _index1, _catalog1, metadata1 = load_or_build_rule_graph_artifacts(self.rules, output_dir=tmpdir)
            self.assertFalse(metadata1["cache_hit"])

            _index2, _catalog2, metadata2 = load_or_build_rule_graph_artifacts(self.rules, output_dir=tmpdir)
            self.assertTrue(metadata2["cache_hit"])

    def test_retrieve_candidates_preserves_hybrid_ranking_and_adds_graph_reasons(self) -> None:
        question = load_question(FIXTURE_DIR / "question_private_fund_nav_warning.json")
        facts, evidence_refs = load_document_bundle(FIXTURE_DIR / "document_bundle_private_fund_nav_warning.json")

        candidates = retrieve_candidates(
            self.rules,
            question,
            min_signal_hits=1,
            top_k=1,
            facts=facts,
            evidence_refs=evidence_refs,
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].rule.rule_id, self.fund_full_rule.rule_id)
        self.assertIn("retrieval_diagnostics", candidates[0].metadata)
        self.assertIn("dense", candidates[0].metadata["retrieval_diagnostics"])
        self.assertIn("cross_rerank", candidates[0].metadata["retrieval_diagnostics"])
        self.assertTrue(any(reason.startswith("graph_community=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("graph_meta_rule=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("graph_rag_hits=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("graph_rag_top_passage=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("dense_score=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("dense_hits=") for reason in candidates[0].reasons))
        self.assertTrue(any(reason.startswith("cross_rerank_score=") for reason in candidates[0].reasons))


if __name__ == "__main__":
    unittest.main()
