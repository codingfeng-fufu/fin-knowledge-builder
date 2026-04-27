from __future__ import annotations

import json
import unittest

from phase1_runtime.kimi_llm_executor import execute_llm_step


class KimiLlmExecutorTests(unittest.TestCase):
    def test_execute_llm_step_falls_back_to_selected_chunks_when_evidence_missing(self) -> None:
        def kimi_client(_payload: dict[str, object]) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "target_price": 8.6,
                                    "valuation_method": "PB",
                                    "valuation_multiple": "0.75x 2026E PB",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = execute_llm_step(
            goal="提取目标价和估值方法。",
            document_chunks=[
                {
                    "chunk_id": "chunk_001",
                    "doc_id": "doc_001",
                    "text": "维持增持评级，目标价8.6元，对应0.75x 2026E PB。",
                    "locator": {"page": 1, "line": 1},
                }
            ],
            prior_outputs={},
            output_schema={
                "type": "object",
                "required": ["target_price", "valuation_method", "valuation_multiple", "evidence_refs"],
                "properties": {
                    "target_price": {"type": "number"},
                    "valuation_method": {"type": "string"},
                    "valuation_multiple": {"type": "string"},
                    "evidence_refs": {"type": "array"},
                },
            },
            constraints={"hints": ["目标价", "PB"], "chunk_top_k": 4},
            kimi_client=kimi_client,
        )

        self.assertEqual(result["target_price"], 8.6)
        self.assertEqual(result["valuation_method"], "PB")
        self.assertGreaterEqual(len(result["evidence_refs"]), 1)
        self.assertEqual(result["evidence_refs"][0]["doc_id"], "doc_001")
        self.assertEqual(result["evidence_refs"][0]["snippet_id"], "chunk_001")

    def test_execute_llm_step_keeps_empty_evidence_when_nothing_extracted(self) -> None:
        def kimi_client(_payload: dict[str, object]) -> dict[str, object]:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "target_price": None,
                                    "valuation_method": None,
                                    "valuation_multiple": None,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            }

        result = execute_llm_step(
            goal="提取目标价和估值方法。",
            document_chunks=[
                {
                    "chunk_id": "chunk_001",
                    "doc_id": "doc_001",
                    "text": "本页未提供目标价。",
                    "locator": {"page": 1, "line": 1},
                }
            ],
            prior_outputs={},
            output_schema={
                "type": "object",
                "required": ["target_price", "valuation_method", "valuation_multiple", "evidence_refs"],
                "properties": {
                    "target_price": {"type": "number"},
                    "valuation_method": {"type": "string"},
                    "valuation_multiple": {"type": "string"},
                    "evidence_refs": {"type": "array"},
                },
            },
            constraints={"hints": ["目标价", "PB"], "chunk_top_k": 4},
            kimi_client=kimi_client,
        )

        self.assertEqual(result["evidence_refs"], [])


if __name__ == "__main__":
    unittest.main()
