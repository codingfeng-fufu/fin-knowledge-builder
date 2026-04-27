"""Mock Kimi client for unit tests.

Provides a MockKimiExtractor that returns pre-defined extraction results
without calling the real Kimi API.
"""
from __future__ import annotations

import json
import re
from typing import Any


class MockKimiExtractor:
    """
    Mock transport callable for kimi_llm_executor.execute_llm_step().

    Inspects the output_schema in the prompt to determine what keys to return,
    then looks up pre-configured values for those keys.

    Usage:
        mock = MockKimiExtractor({
            "current_nav": 0.72,
            "warning_threshold": 0.80,
            "contract_requires_warning": True,
        })
        runtime.run(..., kimi_client=mock)
    """

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = dict(values)

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        user_content = payload["messages"][-1]["content"]

        # Parse the output schema section from the extraction prompt
        schema_match = re.search(
            r"OUTPUT SCHEMA.*?(\{.*?\})\s*\n\nInstructions",
            user_content,
            re.DOTALL,
        )
        result: dict[str, Any] = {}
        if schema_match:
            try:
                schema = json.loads(schema_match.group(1))
                for key in schema.get("required", []):
                    if key == "evidence_refs":
                        result[key] = [
                            {
                                "doc_id": "mock_doc",
                                "snippet_id": f"mock_{key}",
                                "text": f"[mock evidence for {key}]",
                            }
                        ]
                    elif key in self.values:
                        result[key] = self.values[key]
            except (json.JSONDecodeError, KeyError):
                pass

        if not result:
            result = {"evidence_refs": []}

        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(result, ensure_ascii=False)
                    }
                }
            ]
        }


# Convenience: pre-built mocks for the two demo scenarios

FUND_NAV_MOCK_VALUES = {
    "current_nav": 0.72,
    "warning_threshold": 0.80,
    "contract_requires_warning": True,
}

FUND_NAV_NO_BREACH_MOCK_VALUES = {
    "current_nav": 0.85,
    "warning_threshold": 0.80,
    "contract_requires_warning": True,
}

CREDIT_NOTICE_MOCK_VALUES = {
    "days_to_maturity": 3,
    "notice_threshold_days": 5,
    "contract_requires_notice": True,
}

CREDIT_NO_NOTICE_MOCK_VALUES = {
    "days_to_maturity": 20,
    "notice_threshold_days": 5,
    "contract_requires_notice": True,
}

EQUITY_RESEARCH_MOCK_VALUES = {
    "analyst_rating": "增持",
    "rating_change": "维持",
    "rating_rationale": "息差压力缓解，资产质量稳中有进，高股息具备吸引力。",
    "target_price": 8.6,
    "valuation_method": "PB",
    "valuation_multiple": "0.75x 2026E PB",
    "upside_description": "+13%空间",
    "key_risks": "①零售不良超预期；②LPR再度大幅下调；③债市急跌导致投资收益亏损",
    "risk_count": 3,
    "answer_text": "研报维持增持评级，目标价8.6元，基于0.75x 2026E PB，主要下行风险包括零售不良、LPR下调和债市波动。",
    "decision": "rating_bullish",
}
