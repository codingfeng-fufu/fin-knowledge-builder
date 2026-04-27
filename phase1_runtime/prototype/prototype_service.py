from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

from ..datasets import run_full_workflow
from ..registry.registry_store import DEFAULT_DB_PATH
from ..runtime_core import Phase1Runtime
from ..schema import load_document_bundle, load_question, load_rule


DEFAULT_PROTOTYPE_WORK_DIR = Path("phase1_runtime/prototype_runs")
FUND_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
CREDIT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_credit_001")
EQUITY_RESEARCH_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_equity_research_001")
FUND_ATOMIC_RULE_FIXTURES = [
    Path("phase1_runtime/fixtures/rule_atomic_numeric_threshold_breach.json"),
    Path("phase1_runtime/fixtures/rule_atomic_contractual_warning_gate.json"),
    Path("phase1_runtime/fixtures/rule_atomic_policy_answer_builder.json"),
]
CREDIT_ATOMIC_RULE_FIXTURES = [
    Path("phase1_runtime/fixtures/rule_atomic_notice_window_open.json"),
    Path("phase1_runtime/fixtures/rule_atomic_contractual_notice_gate.json"),
    Path("phase1_runtime/fixtures/rule_atomic_notice_answer_builder.json"),
]
EQUITY_RESEARCH_ATOMIC_RULE_FIXTURES = [
    Path("phase1_runtime/fixtures/rule_atomic_research_rating_view.json"),
    Path("phase1_runtime/fixtures/rule_atomic_research_target_price.json"),
    Path("phase1_runtime/fixtures/rule_atomic_research_key_risks.json"),
]


PROTOTYPE_FLOWS: dict[str, dict[str, Any]] = {
    "fund_direct": {
        "title": "Fund Direct Match",
        "description": "完整规则直接覆盖当前问题，展示最短执行链路。",
        "source_dataset_dir": FUND_DATASET_DIR,
        "mode": "direct",
        "recommended": False,
    },
    "fund_compose": {
        "title": "Fund Composition",
        "description": "没有整题规则时，系统用 Atomic Rules 受控组合出净值预警结论。",
        "source_dataset_dir": FUND_DATASET_DIR,
        "mode": "atomic_composition",
        "fixture_paths": FUND_ATOMIC_RULE_FIXTURES,
        "recommended": False,
    },
    "credit_compose": {
        "title": "Credit Composition",
        "description": "第二个业务族样本，展示规则组合不是单一案例技巧。",
        "source_dataset_dir": CREDIT_DATASET_DIR,
        "mode": "atomic_composition",
        "fixture_paths": CREDIT_ATOMIC_RULE_FIXTURES,
        "recommended": True,
    },
    "equity_research_direct": {
        "title": "Equity Research Direct Match",
        "description": "股票研报整题规则直接输出评级、目标价和主要下行风险。",
        "source_dataset_dir": EQUITY_RESEARCH_DATASET_DIR,
        "mode": "direct",
        "recommended": False,
    },
}


def list_prototype_flows() -> dict[str, Any]:
    flows = []
    for flow_id, config in PROTOTYPE_FLOWS.items():
        flows.append(
            {
                "flow_id": flow_id,
                "title": config["title"],
                "description": config["description"],
                "mode": config["mode"],
                "recommended": bool(config.get("recommended", False)),
            }
        )
    return {
        "flow_count": len(flows),
        "recommended_flow_id": next((flow["flow_id"] for flow in flows if flow["recommended"]), flows[0]["flow_id"]),
        "flows": flows,
    }


def _prepare_clean_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _materialize_atomic_dataset(
    source_dataset_dir: Path,
    fixture_paths: list[Path],
    output_dir: Path,
) -> Path:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(source_dataset_dir, output_dir)

    atomic_rules = [json.loads(path.read_text(encoding="utf-8")) for path in fixture_paths]
    atomic_rule_objects = [load_rule(path) for path in fixture_paths]
    (output_dir / "rule_pool.json").write_text(
        json.dumps(atomic_rules, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    question = load_question(output_dir / "question_struct.json")
    facts, evidence_refs = load_document_bundle(output_dir / "document_bundle.json")
    runtime = Phase1Runtime(trace_dir=output_dir / "seed_traces", retrieval_top_k=8)
    seeded_result = runtime.run(
        question=question,
        rules=atomic_rule_objects,
        facts=facts,
        evidence_refs=evidence_refs,
    )
    seeded_trace = json.loads(seeded_result.trace_path.read_text(encoding="utf-8"))
    (output_dir / "execution_trace.json").write_text(
        json.dumps(seeded_trace, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    simulation_dataset = json.loads((output_dir / "simulation_dataset.json").read_text(encoding="utf-8"))
    simulation_dataset["rule_pool"] = atomic_rules
    simulation_dataset["execution_trace"] = seeded_trace
    (output_dir / "simulation_dataset.json").write_text(
        json.dumps(simulation_dataset, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_materials(dataset_dir: Path) -> dict[str, Any]:
    case_record = _read_json(dataset_dir / "case_record.json")
    question_struct = _read_json(dataset_dir / "question_struct.json")
    document_bundle = _read_json(dataset_dir / "document_bundle.json")
    documents = document_bundle.get("documents", [])
    evidence_refs = document_bundle.get("evidence_refs", [])
    return {
        "case_id": case_record.get("case_id"),
        "case_title": case_record.get("title"),
        "question_text": question_struct.get("question_text"),
        "question_struct": question_struct,
        "documents": [
            {
                "doc_id": item.get("doc_id"),
                "doc_type": item.get("doc_type"),
                "title": item.get("title"),
            }
            for item in documents
        ],
        "facts": dict(document_bundle.get("facts", {})),
        "evidence_refs": [
            {
                "doc_id": item.get("doc_id"),
                "snippet_id": item.get("snippet_id"),
                "text": (item.get("text") or "")[:90],
            }
            for item in evidence_refs
        ],
        "evidence_count": len(evidence_refs),
    }


def _default_feedback_type(route_decision: str, prototype_status: str) -> str:
    if route_decision == "exploration":
        return "missed_rule"
    if prototype_status != "completed" and route_decision == "rule_composable":
        return "composition_failure"
    return "prototype_observation"


def _suggest_rule_ids(rerun: dict[str, Any]) -> list[str]:
    source_rule_ids = list(rerun.get("rerun_source_rule_ids", []))
    if source_rule_ids:
        return source_rule_ids
    matched_rule_id = rerun.get("rerun_matched_rule_id")
    return [] if matched_rule_id is None else [matched_rule_id]


def _route_explanation(route_decision: str) -> str:
    if route_decision == "direct_match":
        return "已知问题越来越稳：系统直接命中完整规则，以最短路径执行。"
    if route_decision == "rule_composable":
        return "半已知问题越来越快：系统没有整题规则，但可以由已有 Atomic Rules 受控组合出新解法。"
    return "当前没有完整规则也无法可靠组合，只能进入 exploration fallback。"


def _solution_view(materials: dict[str, Any], workflow: dict[str, Any], rerun: dict[str, Any], feedback_defaults: dict[str, Any]) -> dict[str, Any]:
    replay = workflow["replay_summary"]
    question_struct = materials["question_struct"]
    candidate_rules = replay.get("candidate_rules", [])
    atomic_candidate_count = sum(1 for item in candidate_rules if item.get("rule_kind") == "atomic")
    composite_candidate_count = sum(1 for item in candidate_rules if item.get("rule_kind") != "atomic")
    return {
        "input": {
            "question_text": materials["question_text"],
            "case_id": materials["case_id"],
            "case_title": materials["case_title"],
            "documents": materials["documents"],
            "evidence_refs": materials["evidence_refs"],
            "evidence_count": materials["evidence_count"],
        },
        "structured_understanding": {
            "question_types": question_struct.get("question_types", []),
            "intents": question_struct.get("intents", []),
            "document_types": question_struct.get("document_types", []),
            "extracted_inputs": question_struct.get("extracted_inputs", {}),
            "facts": materials["facts"],
        },
        "retrieval": {
            "candidate_rules": candidate_rules,
            "matched_rule_id": rerun.get("rerun_matched_rule_id"),
            "source_rule_ids": rerun.get("rerun_source_rule_ids", []),
            "asset_counts": {
                "candidate_total": len(candidate_rules),
                "atomic_candidates": atomic_candidate_count,
                "composite_or_full_candidates": composite_candidate_count,
            },
        },
        "route": {
            "route_decision": rerun.get("rerun_route_decision"),
            "composition_pattern": rerun.get("rerun_composition_pattern"),
            "explanation": _route_explanation(rerun.get("rerun_route_decision")),
        },
        "execution": {
            "timeline": replay.get("timeline", []),
            "step_order": replay.get("step_order", []),
            "validator_failures": replay.get("validator_failures", []),
            "trace_id": rerun.get("rerun_trace_id"),
            "trace_path": rerun.get("rerun_trace_path"),
            "final_decision": rerun.get("rerun_final_decision"),
            "final_answer": rerun.get("rerun_final_answer"),
        },
        "feedback": feedback_defaults,
    }


def run_prototype_flow(
    flow_id: str,
    work_dir: str | Path = DEFAULT_PROTOTYPE_WORK_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    if flow_id not in PROTOTYPE_FLOWS:
        raise FileNotFoundError(f"prototype flow not found: {flow_id}")

    config = PROTOTYPE_FLOWS[flow_id]
    prototype_root = _prepare_clean_dir(Path(work_dir) / flow_id)
    trace_dir = prototype_root / "workflow_traces"

    if config["mode"] == "direct":
        dataset_dir = Path(config["source_dataset_dir"])
    elif config["mode"] == "atomic_composition":
        dataset_dir = _materialize_atomic_dataset(
            source_dataset_dir=Path(config["source_dataset_dir"]),
            fixture_paths=list(config["fixture_paths"]),
            output_dir=prototype_root / "dataset",
        )
    else:
        raise ValueError(f"unsupported prototype mode {config['mode']}")

    workflow = run_full_workflow(dataset_dir=dataset_dir, trace_dir=trace_dir, db_path=db_path)
    rerun = workflow["rerun_summary"]
    materials = _load_materials(Path(dataset_dir))
    feedback_type = _default_feedback_type(rerun["rerun_route_decision"], workflow["workflow_status"])
    feedback_defaults = {
        "trace_id": rerun["rerun_trace_id"],
        "case_id": materials["case_id"],
        "route_decision": rerun["rerun_route_decision"],
        "feedback_type": feedback_type,
        "rule_ids": _suggest_rule_ids(rerun),
        "payload": {
            "flow_id": flow_id,
            "flow_title": config["title"],
            "prototype_status": workflow["workflow_status"],
            "final_decision": rerun["rerun_final_decision"],
            "final_answer": rerun["rerun_final_answer"],
        },
    }

    return {
        "flow_id": flow_id,
        "title": config["title"],
        "description": config["description"],
        "mode": config["mode"],
        "recommended": bool(config.get("recommended", False)),
        "prototype_status": workflow["workflow_status"],
        "dataset_dir": str(Path(dataset_dir).resolve()),
        "trace_dir": str(trace_dir.resolve()),
        "case_id": materials["case_id"],
        "case_title": materials["case_title"],
        "question_text": materials["question_text"],
        "route_decision": rerun["rerun_route_decision"],
        "matched_rule_id": rerun["rerun_matched_rule_id"],
        "composition_pattern": rerun["rerun_composition_pattern"],
        "source_rule_ids": rerun["rerun_source_rule_ids"],
        "final_decision": rerun["rerun_final_decision"],
        "final_answer": rerun["rerun_final_answer"],
        "rerun_trace_id": rerun["rerun_trace_id"],
        "rerun_trace_path": rerun["rerun_trace_path"],
        "feedback_defaults": feedback_defaults,
        "solution_view": _solution_view(materials, workflow, rerun, feedback_defaults),
        "workflow": workflow,
    }
