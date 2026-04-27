from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

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
from ..schema import load_document_bundle, load_question
from ..contracts import write_validation_summary


DEFAULT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_credit_001")
DEFAULT_FIXTURE_DIR = Path("phase1_runtime/fixtures")
DEFAULT_TRACE_DIR_NAME = "traces"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _build_documents() -> list[DocumentRecord]:
    return [
        DocumentRecord(
            doc_id="loan_contract_001",
            doc_type="contract",
            title="贷款合同 001",
            language="zh-CN",
            source="simulated_credit_contract_repository",
            tags=["credit", "extension", "notice"],
            metadata={"product": "corporate_loan", "version": "2026-03"},
        ),
        DocumentRecord(
            doc_id="loan_schedule_2026_001",
            doc_type="schedule",
            title="贷款还款计划 001",
            language="zh-CN",
            source="simulated_credit_schedule_repository",
            tags=["credit", "maturity_schedule"],
            metadata={"product": "corporate_loan", "period": "2026-04"},
        ),
    ]


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


def generate_credit_simulation_dataset(output_dir: str | Path = DEFAULT_DATASET_DIR) -> dict[str, object]:
    fixture_dir = DEFAULT_FIXTURE_DIR
    output_root = Path(output_dir)
    trace_dir = output_root / DEFAULT_TRACE_DIR_NAME
    generated_at = _timestamp()

    catalog = RuleCatalog.from_path(fixture_dir, pattern="rule*.json")
    question = load_question(fixture_dir / "question_credit_loan_extension_notice.json")
    facts, evidence_refs = load_document_bundle(fixture_dir / "document_bundle_credit_loan_extension_notice.json")

    runtime = Phase1Runtime(trace_dir=trace_dir, min_signal_hits=1, retrieval_top_k=5)
    run_result = runtime.run(question=question, rules=catalog.rules(), facts=facts, evidence_refs=evidence_refs)
    trace_payload = load_trace(run_result.trace_path)
    trace_record = ExecutionTraceRecord.from_dict(trace_payload)

    bundle = DocumentBundleRecord(
        bundle_id="bundle_credit_loan_extension_notice_001",
        scenario_id="credit_loan_extension_notice_v001",
        documents=_build_documents(),
        facts=facts,
        evidence_refs=evidence_refs,
        created_at=generated_at,
        notes="仿真文档包，覆盖贷款合同展期通知条款与还款计划。",
    )

    final_result = trace_payload.get("final_result") or {}
    gold_answer = GoldAnswer(
        answer_text=str(final_result.get("answer_text")),
        decision=str(final_result.get("decision")),
        confidence=0.95,
        explanation=str(final_result.get("explanation")),
        evidence_snippet_ids=[
            item.get("snippet_id")
            for item in final_result.get("evidence_refs", [])
            if isinstance(item, dict) and item.get("snippet_id")
        ],
    )

    case_record = CaseRecord(
        case_id="case_credit_loan_extension_notice_001",
        scenario_id="credit_loan_extension_notice_v001",
        title="贷款展期通知判断",
        question=question,
        document_bundle_id=bundle.bundle_id,
        gold_answer=gold_answer,
        solution_steps=_build_case_steps(trace_payload),
        linked_rule_ids=[rule.rule_id for rule in catalog.rules() if rule.rule_id == run_result.matched_rule_id],
        review_status="approved",
        reviewer="demo_reviewer",
        created_at=generated_at,
    )

    review_task = ReviewTask(
        review_task_id="review_task_credit_loan_extension_notice_001",
        target_type="rule_version",
        target_id=run_result.matched_rule_id or "unknown_rule",
        status="completed",
        assignee="credit_ops_reviewer",
        checklist=[
            ReviewChecklistItem(
                item_id="check_credit_scope",
                label="贷款展期通知场景范围正确",
                status="passed",
                note="问题、合同条款与到期计划均属于贷款展期通知场景。",
            ),
            ReviewChecklistItem(
                item_id="check_notice_evidence",
                label="通知结论证据充分",
                status="passed",
                note="合同通知条款与还款计划同时支持最终通知结论。",
            ),
            ReviewChecklistItem(
                item_id="check_credit_trace",
                label="Trace 可回放且 validator 全通过",
                status="passed",
                note="本次 direct_match 执行成功，无 validator 失败项。",
            ),
        ],
        comments=[
            "该仿真数据用于验证第二类 case 在同一条链路上可被完整消费。",
            "系统应命中 credit.loan_extension_notice.v1，而不是基金净值风险提示规则。",
        ],
        created_at=generated_at,
        completed_at=generated_at,
    )

    dataset = SimulationDataset(
        dataset_id="demo_set_credit_001",
        scenario_name="credit_loan_extension_notice_v001",
        generated_at=generated_at,
        question=question,
        document_bundle=bundle,
        case_record=case_record,
        rule_pool=catalog.rules(),
        review_task=review_task,
        execution_trace=trace_record,
    )

    file_map = dataset.write_to_dir(output_root)
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


if __name__ == "__main__":
    print(json.dumps(generate_credit_simulation_dataset(), ensure_ascii=False, indent=2))
