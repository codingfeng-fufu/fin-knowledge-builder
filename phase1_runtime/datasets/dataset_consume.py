from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from ..factory import merge_rules_for_runtime
from ..registry.registry_store import DEFAULT_DB_PATH
from ..replay import summarize_trace
from ..runtime_core import Phase1Runtime
from .dataset_import import ImportedDataset, import_dataset_dir


DEFAULT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
DEFAULT_RERUN_TRACE_DIR = Path("phase1_runtime/consumption_traces")


def summarize_imported_dataset(imported: ImportedDataset) -> dict[str, Any]:
    final_result = imported.execution_trace.final_result or {}
    return {
        **imported.to_summary(),
        "final_decision": final_result.get("decision"),
        "final_answer": final_result.get("answer_text"),
        "linked_rule_ids": imported.case_record.linked_rule_ids,
        "review_status": imported.case_record.review_status,
        "document_count": len(imported.document_bundle.documents),
        "evidence_count": len(imported.document_bundle.evidence_refs),
    }


def replay_imported_dataset(imported: ImportedDataset) -> dict[str, Any]:
    trace_summary = summarize_trace(imported.execution_trace.to_dict())
    trace_summary["dataset_id"] = imported.simulation_dataset.dataset_id
    trace_summary["scenario_name"] = imported.simulation_dataset.scenario_name
    return trace_summary


def rerun_imported_dataset(
    imported: ImportedDataset,
    trace_dir: str | Path = DEFAULT_RERUN_TRACE_DIR,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    runtime = Phase1Runtime(trace_dir=trace_dir, min_signal_hits=1, retrieval_top_k=5)
    runtime_rules = imported.rule_pool if db_path is None else merge_rules_for_runtime(imported.rule_pool, db_path=db_path)
    rerun = runtime.run(
        question=imported.question,
        rules=runtime_rules,
        facts=imported.document_bundle.facts,
        evidence_refs=imported.document_bundle.evidence_refs,
    )

    stored_result = imported.execution_trace.final_result or {}
    rerun_result = rerun.final_result or {}
    stored_plan = imported.execution_trace.composition_plan or {}
    rerun_plan = rerun.composition_plan or {}

    comparison = {
        "same_status": imported.execution_trace.status == rerun.status,
        "same_route_decision": imported.execution_trace.route_decision == rerun.route_decision,
        "same_matched_rule": imported.execution_trace.retrieval.get("matched_rule_id") == rerun.matched_rule_id,
        "same_final_decision": stored_result.get("decision") == rerun_result.get("decision"),
        "same_final_answer": stored_result.get("answer_text") == rerun_result.get("answer_text"),
        "same_composition_pattern": stored_plan.get("composition_pattern") == rerun_plan.get("composition_pattern"),
        "same_source_rule_ids": stored_plan.get("source_rule_ids", []) == rerun.source_rule_ids,
    }

    return {
        "dataset_id": imported.simulation_dataset.dataset_id,
        "scenario_name": imported.simulation_dataset.scenario_name,
        "stored_trace_id": imported.execution_trace.trace_id,
        "rerun_trace_id": rerun.trace_id,
        "rerun_trace_path": str(Path(rerun.trace_path).resolve()),
        "stored_status": imported.execution_trace.status,
        "rerun_status": rerun.status,
        "stored_route_decision": imported.execution_trace.route_decision,
        "rerun_route_decision": rerun.route_decision,
        "stored_matched_rule_id": imported.execution_trace.retrieval.get("matched_rule_id"),
        "rerun_matched_rule_id": rerun.matched_rule_id,
        "stored_source_rule_ids": stored_plan.get("source_rule_ids", []),
        "rerun_source_rule_ids": rerun.source_rule_ids,
        "stored_composition_pattern": stored_plan.get("composition_pattern"),
        "rerun_composition_pattern": rerun.composition_pattern,
        "stored_final_decision": stored_result.get("decision"),
        "rerun_final_decision": rerun_result.get("decision"),
        "stored_final_answer": stored_result.get("answer_text"),
        "rerun_final_answer": rerun_result.get("answer_text"),
        "runtime_rule_count": len(runtime_rules),
        "comparison": comparison,
        "all_consistent": all(comparison.values()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Consume a validated dataset by summary, replay, or rerun.")
    subparsers = parser.add_subparsers(dest="command")

    summary_parser = subparsers.add_parser("summary", help="Show a compact summary of the imported dataset.")
    summary_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to import.")

    replay_parser = subparsers.add_parser("replay", help="Replay the stored execution trace from the imported dataset.")
    replay_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to import.")

    rerun_parser = subparsers.add_parser("rerun", help="Rerun the runtime with imported assets and compare results.")
    rerun_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to import.")
    rerun_parser.add_argument("--trace-dir", default=str(DEFAULT_RERUN_TRACE_DIR), help="Directory for rerun traces.")
    rerun_parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Factory/registry database for published rules.")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    incoming = list(sys.argv[1:] if argv is None else argv)
    if not incoming or incoming[0] not in {"summary", "replay", "rerun"}:
        incoming = ["summary", *incoming]
    return parser.parse_args(incoming)


def main() -> None:
    args = parse_args()
    imported = import_dataset_dir(args.dataset_dir)

    if args.command == "summary":
        payload = summarize_imported_dataset(imported)
    elif args.command == "replay":
        payload = replay_imported_dataset(imported)
    elif args.command == "rerun":
        payload = rerun_imported_dataset(imported, trace_dir=args.trace_dir, db_path=args.db_path)
    else:
        raise ValueError(f"unsupported command {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
