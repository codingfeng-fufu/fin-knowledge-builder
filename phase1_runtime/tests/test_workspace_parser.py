from __future__ import annotations

from pathlib import Path
import unittest

from phase1_runtime.schema import load_document_bundle, load_question, load_rule
from phase1_runtime.parsing import parse_workspace_bundle


class WorkspaceParserTests(unittest.TestCase):
    def test_parse_fund_bundle_produces_document_chunks(self) -> None:
        dataset_dir = Path("phase1_runtime/sim_data/demo_set_001")
        question = load_question(dataset_dir / "question_struct.json")
        facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
        payload = parse_workspace_bundle(
            question_text="某私募产品最新单位净值为0.72，低于0.80后，是否需要向投资者做风险提示？",
            materials=[
                {
                    "name": "fund_clause.txt",
                    "content": "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。\n最新单位净值为0.72。",
                }
            ],
            scenario_id="fund_nav_warning",
            seed_question=question,
            seed_facts=facts,
            seed_evidence_refs=evidence_refs,
        )
        # New parser: no pre-extraction, returns empty facts
        self.assertEqual(payload["facts"], {})
        # DocumentChunks are produced
        self.assertGreater(len(payload["document_chunks"]), 0)
        self.assertIn("text", payload["document_chunks"][0])
        self.assertIn("locator", payload["document_chunks"][0])
        # Document preview still works
        self.assertEqual(payload["document_packet_preview"]["document_count"], 1)
        # query-aware context is built
        self.assertIn("context_packet", payload)
        self.assertGreater(len(payload["context_packet"]["relevant_blocks"]), 0)
        # evidence_packets expose relevant blocks as evidence
        self.assertGreater(len(payload["evidence_packets"]), 0)
        self.assertGreater(len(payload["evidence_refs"]), 0)

    def test_parse_credit_bundle_with_partial_materials(self) -> None:
        dataset_dir = Path("phase1_runtime/sim_data/demo_set_credit_001")
        question = load_question(dataset_dir / "question_struct.json")
        facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
        payload = parse_workspace_bundle(
            question_text="是否需要发送借款人通知？",
            materials=[
                {
                    "name": "notice_clause.txt",
                    "content": "合同约定在到期前5日内应通知借款人办理展期手续。",
                }
            ],
            scenario_id="credit_notice",
            seed_question=question,
            seed_facts=facts,
            seed_evidence_refs=evidence_refs,
        )
        # New parser: no pre-extraction
        self.assertEqual(payload["facts"], {})
        # DocumentChunks produced
        self.assertGreater(len(payload["document_chunks"]), 0)
        # Document preview works
        self.assertEqual(payload["document_packet_preview"]["document_count"], 1)

    def test_parse_workspace_bundle_builds_fact_sheet_with_evidence_refs(self) -> None:
        dataset_dir = Path("phase1_runtime/sim_data/demo_set_001")
        question = load_question(dataset_dir / "question_struct.json")
        facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
        rule = load_rule(Path("phase1_runtime/fixtures/rule_private_fund_nav_warning.json"))
        payload = parse_workspace_bundle(
            question_text="某私募产品最新单位净值为0.72，低于0.80后，是否需要向投资者做风险提示？",
            materials=[
                {
                    "name": "fund_clause.txt",
                    "content": "基金合同约定：当产品净值低于0.80时，管理人应及时向投资者提示风险。\n最新单位净值为0.72。",
                }
            ],
            scenario_id="fund_nav_warning",
            seed_question=question,
            seed_facts=facts,
            seed_evidence_refs=evidence_refs,
            required_inputs=rule.inputs.required,
        )
        self.assertIn("context_packet", payload)
        self.assertGreater(len(payload["fact_sheet"]), 0)
        grounded_with_evidence = [
            item for item in payload["fact_sheet"]
            if item.get("status") == "grounded" and item.get("evidence_refs")
        ]
        self.assertGreater(len(grounded_with_evidence), 0)

    def test_query_context_prioritizes_direct_rating_block(self) -> None:
        dataset_dir = Path("phase1_runtime/sim_data/demo_set_equity_research_001")
        question = load_question(dataset_dir / "question_struct.json")
        facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
        rule = load_rule(Path("phase1_runtime/fixtures/rule_equity_research_rating_view.json"))
        payload = parse_workspace_bundle(
            question_text="这份研报对工商银行的投资评级是什么？",
            materials=[
                {
                    "name": "research.txt",
                    "content": "投资评级：增持（维持）\n相关说明：公司经营稳健。",
                }
            ],
            scenario_id="equity_research",
            seed_question=question,
            seed_facts=facts,
            seed_evidence_refs=evidence_refs,
            required_inputs=rule.inputs.required,
        )
        self.assertEqual(payload["context_packet"]["query_profile"]["query_mode"], "rating")
        first_block_text = payload["context_packet"]["relevant_blocks"][0]["text"]
        self.assertIn("增持", first_block_text)
