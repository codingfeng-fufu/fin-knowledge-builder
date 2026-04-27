from __future__ import annotations

from pathlib import Path
from typing import Any

from ..registry.registry_store import DEFAULT_DB_PATH
from ..prototype.prototype_service import run_prototype_flow
from .product_catalog import (
    DECISION_TEXT_MAP,
    PRODUCT_SCENARIOS,
    ROUTE_TITLE_MAP,
    build_expert_view,
    get_workspace_contract,
    DEFAULT_PRODUCT_WORK_DIR,
)


def solve_product_request(
    scenario_id: str = "fund_nav_warning",
    question_text: str | None = None,
    work_dir: str | Path = DEFAULT_PRODUCT_WORK_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    if scenario_id not in PRODUCT_SCENARIOS:
        raise FileNotFoundError(f"product scenario not found: {scenario_id}")

    config = PRODUCT_SCENARIOS[scenario_id]
    flow_payload = run_prototype_flow(flow_id=config["flow_id"], work_dir=work_dir, db_path=db_path)
    solution = flow_payload["solution_view"]
    display_question = question_text.strip() if isinstance(question_text, str) and question_text.strip() else solution["input"]["question_text"]
    route_decision = flow_payload["route_decision"]
    final_decision = solution["execution"]["final_decision"]
    final_answer = solution["execution"]["final_answer"]
    workspace_contract = get_workspace_contract()

    return {
        "scenario_id": scenario_id,
        "scenario_title": config["title"],
        "scenario_description": config["description"],
        "question_text": display_question,
        "documents": solution["input"]["documents"],
        "evidence_refs": solution["input"]["evidence_refs"],
        "final_answer": final_answer,
        "final_decision": final_decision,
        "decision_text": DECISION_TEXT_MAP.get(final_decision, final_decision),
        "route_decision": route_decision,
        "route_title": ROUTE_TITLE_MAP.get(route_decision, route_decision),
        "route_explanation": solution["route"]["explanation"],
        "solution_view": solution,
        "feedback_defaults": flow_payload["feedback_defaults"],
        "flow_id": flow_payload["flow_id"],
        "input_mode": "scenario_preview",
        "workspace_contract": workspace_contract,
        "document_parser_contract": workspace_contract["document_parser_contract"],
        "expert_view": build_expert_view(
            scenario_id=scenario_id,
            question_text=display_question,
            final_answer=final_answer,
            final_decision=final_decision,
            route_decision=route_decision,
        ),
        "question_packet_preview": solution["structured_understanding"],
        "document_packet_preview": {
            "document_count": len(solution["input"]["documents"]),
            "documents": solution["input"]["documents"],
            "status": "scenario_sample_mode",
        },
        "fact_sheet": [],
        "parser_status": "scenario_preview",
    }
