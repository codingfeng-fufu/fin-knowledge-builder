from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_trace(path: str | Path) -> dict[str, Any]:
    trace_path = Path(path)
    return json.loads(trace_path.read_text(encoding="utf-8"))


def resolve_trace_path(trace_path: str | Path | None, trace_dir: str | Path) -> Path:
    if trace_path is not None:
        path = Path(trace_path)
        if not path.exists():
            raise FileNotFoundError(f"trace file not found: {path}")
        return path

    trace_root = Path(trace_dir)
    candidates = sorted(trace_root.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"no trace files found in {trace_root}")
    return candidates[0]


def summarize_trace(trace: dict[str, Any]) -> dict[str, Any]:
    retrieval = trace.get("retrieval", {})
    final_result = trace.get("final_result") or {}
    step_contracts = trace.get("step_contracts", [])
    step_results = trace.get("step_results", [])
    validator_results = trace.get("validator_results", [])
    composition_plan = trace.get("composition_plan") or {}
    composition_trace = trace.get("composition_trace") or {}

    step_order = [item.get("step_id") for item in step_results]
    timeline = []
    for contract, result in zip(step_contracts, step_results):
        output = result.get("output", {})
        timeline.append(
            {
                "rule_id": result.get("rule_id") or contract.get("rule_id"),
                "step_id": contract.get("step_id"),
                "goal": contract.get("goal"),
                "output_keys": sorted(output.keys()),
                "composition_role": contract.get("composition_role"),
            }
        )

    failed_validators = [item for item in validator_results if not item.get("ok", False)]

    return {
        "trace_id": trace.get("trace_id"),
        "created_at": trace.get("created_at"),
        "status": trace.get("status"),
        "route_decision": trace.get("route_decision"),
        "matched_rule_id": retrieval.get("matched_rule_id"),
        "candidate_rules": retrieval.get("candidates", []),
        "source_rule_ids": composition_plan.get("source_rule_ids") or retrieval.get("source_rule_ids", []),
        "composition_pattern": composition_plan.get("composition_pattern") or retrieval.get("composition_pattern"),
        "step_order": step_order,
        "timeline": timeline,
        "validator_failures": failed_validators,
        "composition_rule_results": composition_trace.get("rule_results", []),
        "final_decision": final_result.get("decision"),
        "final_answer": final_result.get("answer_text"),
        "failure_reason": trace.get("failure_reason"),
    }
