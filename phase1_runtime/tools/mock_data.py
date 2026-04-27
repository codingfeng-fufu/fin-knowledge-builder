from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

from ..catalog import RuleCatalog
from ..contracts import (
    CaseRecord,
    CaseStep,
    DocumentBundleRecord,
    DocumentRecord,
    ExecutionTraceRecord,
    GoldAnswer,
    ReviewChecklistItem,
    ReviewTask,
    SimulationDataset,
)
from ..replay import load_trace
from ..runtime_core import Phase1Runtime
from ..schema import EvidenceRef, QuestionStruct, load_document_bundle, load_question
from ..contracts import write_validation_summary


DEFAULT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
DEFAULT_BATCH_DIR = Path("phase1_runtime/sim_data/batch_demo_001")
DEFAULT_FIXTURE_DIR = Path("phase1_runtime/fixtures")
DEFAULT_TRACE_DIR_NAME = "traces"


DEFAULT_SCENARIO_VARIANTS: list[dict[str, Any]] = [
    {
        "variant_id": "001",
        "dataset_id": "demo_set_001",
        "scenario_name": "private_fund_nav_warning_v001",
        "question_text": "某私募产品净值跌破0.80后，是否需要向投资者做风险提示？",
        "current_nav": 0.78,
        "warning_threshold": 0.80,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "002",
        "dataset_id": "demo_set_002",
        "scenario_name": "private_fund_nav_warning_v002",
        "question_text": "基金净值低于预警阈值后，要不要给投资者做风险提示？",
        "current_nav": 0.81,
        "warning_threshold": 0.80,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "003",
        "dataset_id": "demo_set_003",
        "scenario_name": "private_fund_nav_warning_v003",
        "question_text": "如果产品净值已经跌破0.80，是否还需要向投资者提示风险？",
        "current_nav": 0.76,
        "warning_threshold": 0.80,
        "contract_requires_warning": False,
    },
    {
        "variant_id": "004",
        "dataset_id": "demo_set_004",
        "scenario_name": "private_fund_nav_warning_v004",
        "question_text": "私募基金净值跌破合同红线后，是否必须做风险提示？",
        "current_nav": 0.73,
        "warning_threshold": 0.75,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "005",
        "dataset_id": "demo_set_005",
        "scenario_name": "private_fund_nav_warning_v005",
        "question_text": "净值降到0.82、合同阈值是0.85时，需要向投资者做风险提示吗？",
        "current_nav": 0.82,
        "warning_threshold": 0.85,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "006",
        "dataset_id": "demo_set_006",
        "scenario_name": "private_fund_nav_warning_v006",
        "question_text": "当前净值高于预警线，还要向投资者做风险提示吗？",
        "current_nav": 0.91,
        "warning_threshold": 0.90,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "007",
        "dataset_id": "demo_set_007",
        "scenario_name": "private_fund_nav_warning_v007",
        "question_text": "净值跌破0.70时，管理人是否应立即给投资者风险提示？",
        "current_nav": 0.69,
        "warning_threshold": 0.70,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "008",
        "dataset_id": "demo_set_008",
        "scenario_name": "private_fund_nav_warning_v008",
        "question_text": "产品净值已经跌破阈值，但合同未要求提示风险，还要通知投资者吗？",
        "current_nav": 0.67,
        "warning_threshold": 0.70,
        "contract_requires_warning": False,
    },
    {
        "variant_id": "009",
        "dataset_id": "demo_set_009",
        "scenario_name": "private_fund_nav_warning_v009",
        "question_text": "当净值低于0.85时，这只产品是否需要向投资者进行风险提示？",
        "current_nav": 0.79,
        "warning_threshold": 0.85,
        "contract_requires_warning": True,
    },
    {
        "variant_id": "010",
        "dataset_id": "demo_set_010",
        "scenario_name": "private_fund_nav_warning_v010",
        "question_text": "如果净值没有跌破合同阈值，还需要做风险提示给投资者吗？",
        "current_nav": 0.86,
        "warning_threshold": 0.85,
        "contract_requires_warning": False,
    },
]


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _variant_doc_ids(variant: dict[str, Any]) -> tuple[str, str]:
    suffix = variant["variant_id"]
    return (f"private_fund_contract_{suffix}", f"private_fund_nav_report_{suffix}")


def _contract_text(threshold: float, contract_requires_warning: bool) -> str:
    if contract_requires_warning:
        return f"当产品净值低于{threshold:.2f}时，管理人应及时向投资者提示风险。"
    return f"合同未约定产品净值低于{threshold:.2f}后必须向投资者提示风险。"


def _nav_text(current_nav: float, variant_id: str) -> str:
    return f"仿真场景 {variant_id} 的最新单位净值为{current_nav:.2f}。"


def _build_documents(variant: dict[str, Any], evidence_refs: list[EvidenceRef]) -> list[DocumentRecord]:
    contract_doc_id, nav_doc_id = _variant_doc_ids(variant)
    records: list[DocumentRecord] = []
    for evidence in evidence_refs:
        if evidence.doc_id == contract_doc_id:
            records.append(
                DocumentRecord(
                    doc_id=evidence.doc_id,
                    doc_type="contract",
                    title=f"私募基金合同 {variant['variant_id']}",
                    language="zh-CN",
                    source="simulated_contract_repository",
                    tags=["private_fund", "risk_disclosure", variant["variant_id"]],
                    metadata={"variant_id": variant["variant_id"], "version": "2026-03"},
                )
            )
        elif evidence.doc_id == nav_doc_id:
            records.append(
                DocumentRecord(
                    doc_id=evidence.doc_id,
                    doc_type="report",
                    title=f"私募基金净值报告 {variant['variant_id']}",
                    language="zh-CN",
                    source="simulated_reporting_system",
                    tags=["private_fund", "nav_report", variant["variant_id"]],
                    metadata={"variant_id": variant["variant_id"], "period": "2026Q1"},
                )
            )
    return records


def _build_case_steps(trace_payload: dict) -> list[CaseStep]:
    steps: list[CaseStep] = []
    contracts = trace_payload.get("step_contracts", [])
    results = trace_payload.get("step_results", [])
    for contract, result in zip(contracts, results):
        output = dict(result.get("output", {}))
        evidence_refs = output.get("evidence_refs", [])
        snippet_ids = [item.get("snippet_id") for item in evidence_refs if isinstance(item, dict) and item.get("snippet_id")]
        steps.append(
            CaseStep(
                step_id=str(contract.get("step_id")),
                description=str(contract.get("goal")),
                tool=str(contract.get("executor", {}).get("tool")),
                inputs=dict(contract.get("inputs", {})),
                expected_output=output,
                evidence_snippet_ids=snippet_ids,
            )
        )
    return steps


def _build_variant_question(base_question: QuestionStruct, variant: dict[str, Any]) -> QuestionStruct:
    return QuestionStruct(
        question_text=str(variant["question_text"]),
        question_types=list(base_question.question_types),
        intents=list(base_question.intents),
        document_types=list(base_question.document_types),
        extracted_inputs=dict(base_question.extracted_inputs),
    )


def _build_variant_facts(base_facts: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    facts = deepcopy(base_facts)
    facts["current_nav"] = float(variant["current_nav"])
    facts["warning_threshold"] = float(variant["warning_threshold"])
    facts["contract_requires_warning"] = bool(variant["contract_requires_warning"])
    return facts


def _build_variant_evidence_refs(variant: dict[str, Any]) -> list[EvidenceRef]:
    contract_doc_id, nav_doc_id = _variant_doc_ids(variant)
    threshold = float(variant["warning_threshold"])
    current_nav = float(variant["current_nav"])
    contract_requires_warning = bool(variant["contract_requires_warning"])

    return [
        EvidenceRef(
            doc_id=contract_doc_id,
            locator={"section": "7.4 风险揭示"},
            snippet_id="snippet_contract_threshold",
            text=_contract_text(threshold, contract_requires_warning),
        ),
        EvidenceRef(
            doc_id=nav_doc_id,
            locator={"page": 2, "section": "净值情况"},
            snippet_id="snippet_nav_table",
            text=_nav_text(current_nav, str(variant["variant_id"])),
        ),
    ]


def _build_gold_answer(trace_payload: dict, variant: dict[str, Any]) -> GoldAnswer:
    final_result = trace_payload.get("final_result") or {}
    decision = str(final_result.get("decision"))
    confidence = 0.96 if decision == "must_warn" else 0.90
    evidence_ids = [
        item.get("snippet_id")
        for item in final_result.get("evidence_refs", [])
        if isinstance(item, dict) and item.get("snippet_id")
    ]
    return GoldAnswer(
        answer_text=str(final_result.get("answer_text")),
        decision=decision,
        confidence=confidence,
        explanation=str(final_result.get("explanation")),
        evidence_snippet_ids=evidence_ids,
    )


def _build_review_task(generated_at: str, variant: dict[str, Any], matched_rule_id: str | None, trace_payload: dict) -> ReviewTask:
    final_result = trace_payload.get("final_result") or {}
    decision = str(final_result.get("decision"))
    return ReviewTask(
        review_task_id=f"review_task_{variant['dataset_id']}",
        target_type="rule_version",
        target_id=matched_rule_id or "unknown_rule",
        status="completed",
        assignee="risk_ops_reviewer",
        checklist=[
            ReviewChecklistItem(
                item_id="check_question_scope",
                label="问题类型与规则范围一致",
                status="passed",
                note=f"场景 {variant['variant_id']} 命中规则 {matched_rule_id}。",
            ),
            ReviewChecklistItem(
                item_id="check_evidence_chain",
                label="关键结论有证据链",
                status="passed",
                note=f"最终决策为 {decision}，合同与净值证据均已引用。",
            ),
            ReviewChecklistItem(
                item_id="check_runtime_trace",
                label="Trace 可回放且 validator 全通过",
                status="passed",
                note="本次 Direct Match 执行完成，validator 无失败项。",
            ),
        ],
        comments=[
            f"仿真场景 {variant['variant_id']} 用于验证 Direct Match 主链的稳定性。",
            "候选规则池保留一条无关规则，用于测试检索排序与门槛过滤。",
        ],
        created_at=generated_at,
        completed_at=generated_at,
    )


def generate_simulation_dataset(
    output_dir: str | Path = DEFAULT_DATASET_DIR,
    variant: dict[str, Any] | None = None,
) -> dict[str, object]:
    fixture_dir = DEFAULT_FIXTURE_DIR
    chosen_variant = dict(DEFAULT_SCENARIO_VARIANTS[0] if variant is None else variant)
    output_root = Path(output_dir)
    trace_dir = output_root / DEFAULT_TRACE_DIR_NAME
    generated_at = _timestamp()

    catalog = RuleCatalog.from_path(fixture_dir, pattern="rule*.json")
    base_question = load_question(fixture_dir / "question_private_fund_nav_warning.json")
    base_facts, _base_evidence_refs = load_document_bundle(fixture_dir / "document_bundle_private_fund_nav_warning.json")

    question = _build_variant_question(base_question, chosen_variant)
    facts = _build_variant_facts(base_facts, chosen_variant)
    evidence_refs = _build_variant_evidence_refs(chosen_variant)

    runtime = Phase1Runtime(trace_dir=trace_dir, min_signal_hits=1, retrieval_top_k=5)
    run_result = runtime.run(question=question, rules=catalog.rules(), facts=facts, evidence_refs=evidence_refs)
    trace_payload = load_trace(run_result.trace_path)
    trace_record = ExecutionTraceRecord.from_dict(trace_payload)

    bundle = DocumentBundleRecord(
        bundle_id=f"bundle_{chosen_variant['dataset_id']}",
        scenario_id=str(chosen_variant["scenario_name"]),
        documents=_build_documents(chosen_variant, evidence_refs),
        facts=facts,
        evidence_refs=evidence_refs,
        created_at=generated_at,
        notes=f"仿真文档包 {chosen_variant['variant_id']}，覆盖合同条款与净值报告。",
    )

    case_record = CaseRecord(
        case_id=f"case_{chosen_variant['dataset_id']}",
        scenario_id=str(chosen_variant["scenario_name"]),
        title=f"私募产品净值风险提示判断 {chosen_variant['variant_id']}",
        question=question,
        document_bundle_id=bundle.bundle_id,
        gold_answer=_build_gold_answer(trace_payload, chosen_variant),
        solution_steps=_build_case_steps(trace_payload),
        linked_rule_ids=[rule.rule_id for rule in catalog.rules() if rule.rule_id == run_result.matched_rule_id],
        review_status="approved",
        reviewer="demo_reviewer",
        created_at=generated_at,
    )

    review_task = _build_review_task(generated_at, chosen_variant, run_result.matched_rule_id, trace_payload)

    dataset = SimulationDataset(
        dataset_id=str(chosen_variant["dataset_id"]),
        scenario_name=str(chosen_variant["scenario_name"]),
        generated_at=generated_at,
        question=question,
        document_bundle=bundle,
        case_record=case_record,
        rule_pool=catalog.rules(),
        review_task=review_task,
        execution_trace=trace_record,
    )

    file_map = dataset.write_to_dir(output_root)
    final_result = trace_payload.get("final_result") or {}
    summary = {
        "dataset_id": dataset.dataset_id,
        "scenario_name": dataset.scenario_name,
        "generated_at": dataset.generated_at,
        "matched_rule_id": run_result.matched_rule_id,
        "status": run_result.status,
        "final_decision": final_result.get("decision"),
        "question_text": question.question_text,
        "output_dir": str(output_root.resolve()),
        "files": file_map,
    }
    summary_path = output_root / "generation_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    validation_summary = write_validation_summary(output_root)
    summary["summary_file"] = str(summary_path)
    summary["validation"] = validation_summary
    summary["validation_valid"] = bool(validation_summary.get("valid"))
    return summary


def generate_batch_simulation_datasets(
    output_dir: str | Path = DEFAULT_BATCH_DIR,
    variant_configs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    variants = list(DEFAULT_SCENARIO_VARIANTS if variant_configs is None else variant_configs)

    dataset_summaries: list[dict[str, Any]] = []
    decision_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for variant in variants:
        dataset_dir = root / str(variant["dataset_id"])
        summary = generate_simulation_dataset(output_dir=dataset_dir, variant=variant)
        dataset_summaries.append(summary)

        final_decision = str(summary.get("final_decision"))
        decision_counts[final_decision] = decision_counts.get(final_decision, 0) + 1
        status = str(summary.get("status"))
        status_counts[status] = status_counts.get(status, 0) + 1

    batch_manifest = {
        "batch_id": root.name,
        "generated_at": _timestamp(),
        "dataset_count": len(dataset_summaries),
        "decision_counts": decision_counts,
        "status_counts": status_counts,
        "datasets": dataset_summaries,
    }
    manifest_path = root / "batch_manifest.json"
    manifest_path.write_text(json.dumps(batch_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_manifest["manifest_file"] = str(manifest_path)
    return batch_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate single or batch simulated datasets for Phase 1.")
    subparsers = parser.add_subparsers(dest="command")

    single_parser = subparsers.add_parser("single", help="Generate one simulated dataset.")
    single_parser.add_argument("--output-dir", default=str(DEFAULT_DATASET_DIR), help="Directory for the single dataset output.")
    single_parser.add_argument("--variant-id", default="001", help="Scenario variant id to materialize.")

    batch_parser = subparsers.add_parser("batch", help="Generate a batch of simulated datasets.")
    batch_parser.add_argument("--output-dir", default=str(DEFAULT_BATCH_DIR), help="Directory for the batch dataset output.")
    batch_parser.add_argument("--count", default=len(DEFAULT_SCENARIO_VARIANTS), type=int, help="How many predefined variants to emit.")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    incoming = list(sys.argv[1:] if argv is None else argv)
    if not incoming or incoming[0] not in {"single", "batch"}:
        incoming = ["single", *incoming]
    return parser.parse_args(incoming)


def _variant_by_id(variant_id: str) -> dict[str, Any]:
    for variant in DEFAULT_SCENARIO_VARIANTS:
        if str(variant["variant_id"]) == variant_id:
            return variant
    raise ValueError(f"unknown variant_id {variant_id}")


def main() -> None:
    args = parse_args()
    if args.command == "single":
        payload = generate_simulation_dataset(output_dir=args.output_dir, variant=_variant_by_id(args.variant_id))
    elif args.command == "batch":
        payload = generate_batch_simulation_datasets(
            output_dir=args.output_dir,
            variant_configs=DEFAULT_SCENARIO_VARIANTS[: args.count],
        )
    else:
        raise ValueError(f"unsupported command {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
