from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..factory import merge_rules_for_runtime
from ..parsing import parse_uploaded_materials, parse_workspace_bundle
from ..retrieval import CaseMatch, retrieve_candidates, retrieve_similar_cases, should_shortcut
from ..runtime_flags import runtime_rules_disabled
from ..runtime_core import Phase1Runtime, RuntimeResult, bind_rule, build_task_context
from ..schema import EvidenceRef, load_document_bundle, load_question, load_rule
from .product_catalog import PRODUCT_SCENARIOS, SCENARIO_RULE_PATHS, infer_scenario
from .workspace_support import (
    _display_rule_binding,
    _grounded_retrieval_fact_keys,
    _should_allow_shortcut,
)


def _scenario_seed_bundle(scenario_id: str) -> dict[str, Any]:
    dataset_dir = Path(PRODUCT_SCENARIOS[scenario_id]["source_dataset_dir"])
    question = load_question(dataset_dir / "question_struct.json")
    facts, evidence_refs = load_document_bundle(dataset_dir / "document_bundle.json")
    from ..prototype.prototype_service import _load_materials

    materials = _load_materials(dataset_dir)
    return {
        "dataset_dir": dataset_dir,
        "question": question,
        "facts": facts,
        "evidence_refs": evidence_refs,
        "documents": materials["documents"],
        "case_id": materials["case_id"],
        "case_title": materials["case_title"],
    }


def _workspace_rules(scenario_id: str, db_path: str | Path) -> list[Any]:
    base_rules = [load_rule(path) for path in SCENARIO_RULE_PATHS[scenario_id]]
    return merge_rules_for_runtime(base_rules, db_path=db_path)


def _should_prioritize_equity_research_audit_rule(question_text: str, scenario_id: str) -> bool:
    if scenario_id != "equity_research":
        return False
    lowered = question_text.lower()
    return (
        ("python" in lowered or "代码" in question_text)
        and "收盘价" in question_text
        and "评级" in question_text
        and any(token in question_text for token in ("PE", "PB", "每股盈利", "每股净资产", "估值简表", "复算", "核验"))
    )


def _scenario_rule_ids(scenario_id: str) -> list[str]:
    if runtime_rules_disabled():
        return []
    return [load_rule(path).rule_id for path in SCENARIO_RULE_PATHS[scenario_id]]


def _fallback_documents(seed_bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "source_type": "scenario_default",
            "parse_status": "scenario_default",
        }
        for item in seed_bundle["documents"]
    ]


def _parsed_material_text(item: dict[str, Any]) -> str:
    content = str(item.get("content") or "").strip()
    if content:
        return content
    line_items = item.get("line_items")
    if isinstance(line_items, list) and line_items:
        return "\n".join(str(line.get("text", "")).strip() for line in line_items if str(line.get("text", "")).strip())
    return ""


def _resolve_workspace_scenario_and_parse(
    *,
    question_text: str,
    materials: list[dict[str, Any]],
    scenario_id: str | None,
) -> tuple[str, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    effective_question = question_text.strip() if question_text.strip() else "请根据材料给出处理建议。"
    if scenario_id is None:
        preview_parse_result = parse_uploaded_materials(materials, "fund_nav_warning", question_text=effective_question)
        resolved_scenario_id, scenario_reason = infer_scenario(effective_question, preview_parse_result["parsed_materials"])
        document_parse_result = (
            preview_parse_result
            if resolved_scenario_id == "fund_nav_warning"
            else parse_uploaded_materials(materials, resolved_scenario_id, question_text=effective_question)
        )
    else:
        resolved_scenario_id = scenario_id
        scenario_reason = {"selected_scenario_id": scenario_id, "mode": "manual_override"}
        document_parse_result = parse_uploaded_materials(materials, scenario_id, question_text=effective_question)
    return (
        effective_question,
        scenario_reason,
        document_parse_result,
        document_parse_result["parsed_materials"],
    )


def _prepare_workspace_rules(
    *,
    question_text: str,
    scenario_id: str,
    db_path: str | Path,
) -> tuple[list[Any], list[Any]]:
    rules = _workspace_rules(scenario_id, db_path=db_path)
    if _should_prioritize_equity_research_audit_rule(question_text, scenario_id):
        rules = [rule for rule in rules if rule.rule_id == "equity_research.rating_target_audit.v1"]
    all_required_inputs = [
        field
        for rule in rules
        for field in rule.inputs.required
    ]
    seen_keys: set[str] = set()
    unique_required_inputs = []
    for field in all_required_inputs:
        if field.key not in seen_keys:
            seen_keys.add(field.key)
            unique_required_inputs.append(field)
    return rules, unique_required_inputs


def _build_workspace_runtime_inputs(
    *,
    effective_question: str,
    scenario_id: str,
    parsed_materials: list[dict[str, Any]],
    seed_bundle: dict[str, Any],
    required_inputs: list[Any],
    rules: list[Any],
    db_path: str | Path,
) -> dict[str, Any]:
    parser_bundle = parse_workspace_bundle(
        question_text=effective_question,
        materials=parsed_materials,
        scenario_id=scenario_id,
        seed_question=seed_bundle["question"],
        seed_facts=seed_bundle["facts"],
        seed_evidence_refs=seed_bundle["evidence_refs"],
        required_inputs=required_inputs,
    )

    documents = parser_bundle["documents"] or _fallback_documents(seed_bundle)
    if not parser_bundle["documents"]:
        parser_bundle["document_packet_preview"] = {
            "document_count": len(documents),
            "documents": documents,
            "status": "scenario_default_documents",
        }

    evidence_refs: list[EvidenceRef] = list(parser_bundle["evidence_refs"])
    evidence_packets = parser_bundle["evidence_packets"]
    document_chunks: list[dict[str, Any]] = parser_bundle.get("document_chunks", [])
    retrieval_fact_keys = _grounded_retrieval_fact_keys(parser_bundle["fact_sheet"])

    candidates = retrieve_candidates(
        rules,
        parser_bundle["question"],
        facts=parser_bundle["facts"],
        evidence_refs=evidence_refs,
        retrieval_fact_keys=retrieval_fact_keys,
    )
    task_context = build_task_context(
        question_text=effective_question,
        scenario_hint=scenario_id,
        parser_status=parser_bundle["parser_status"],
        documents=documents,
        fact_sheet=parser_bundle["fact_sheet"],
        evidence_packets=evidence_packets,
        unresolved_slots=parser_bundle["missing_fact_keys"],
        document_chunks=document_chunks,
    )
    rule_by_id = {rule.rule_id: rule for rule in rules}
    rule_bindings = [
        bind_rule(
            rule_by_id[c.rule.rule_id],
            task_context,
            retrieval_score=c.score,
            retrieval_reasons=c.reasons,
            eligible_for_direct_match=c.eligible_for_direct_match,
            eligible_for_composition=c.eligible_for_composition,
        )
        for c in candidates
        if c.rule.rule_id in rule_by_id
    ]
    rule_bindings_payload = [
        _display_rule_binding(item, rule_by_id[item.rule_id])
        for item in rule_bindings
        if item.rule_id in rule_by_id
    ]
    document_full_text = "\n\n".join(
        text for text in (_parsed_material_text(item) for item in parsed_materials) if text
    )
    return {
        "parser_bundle": parser_bundle,
        "documents": documents,
        "evidence_refs": evidence_refs,
        "evidence_packets": evidence_packets,
        "document_chunks": document_chunks,
        "document_full_text": document_full_text,
        "retrieval_fact_keys": retrieval_fact_keys,
        "task_context": task_context,
        "rule_by_id": rule_by_id,
        "rule_bindings": rule_bindings,
        "rule_bindings_payload": rule_bindings_payload,
    }


def _run_workspace_runtime(
    *,
    effective_question: str,
    scenario_id: str,
    normalized_materials: list[dict[str, Any]],
    rules: list[Any],
    parser_bundle: dict[str, Any],
    evidence_refs: list[EvidenceRef],
    retrieval_fact_keys: set[str],
    task_context: Any,
    rule_bindings: list[Any],
    document_chunks: list[dict[str, Any]],
    document_full_text: str,
    effective_kimi_client: Any | None,
    trace_dir: Path,
    db_path: str | Path,
) -> tuple[Any, dict[str, Any], list[CaseMatch], CaseMatch | None]:
    similar_cases = retrieve_similar_cases(effective_question, scenario_id, db_path=db_path)
    shortcut_case = should_shortcut(similar_cases) if _should_allow_shortcut(normalized_materials) else None
    if shortcut_case is not None:
        runtime_result = _make_shortcut_runtime_result(shortcut_case, trace_dir)
    else:
        runtime = Phase1Runtime(trace_dir=trace_dir, retrieval_top_k=8)
        runtime_result = runtime.run(
            question=parser_bundle["question"],
            rules=rules,
            facts=parser_bundle["facts"],
            evidence_refs=evidence_refs,
            retrieval_fact_keys=retrieval_fact_keys,
            task_context=task_context,
            rule_bindings=rule_bindings,
            document_chunks=document_chunks,
            document_full_text=document_full_text,
            kimi_client=effective_kimi_client,
        )
    trace_payload = json.loads(runtime_result.trace_path.read_text(encoding="utf-8"))
    return runtime_result, trace_payload, similar_cases, shortcut_case


def _make_shortcut_runtime_result(case: "CaseMatch", trace_dir: Path) -> RuntimeResult:
    from datetime import UTC, datetime
    from uuid import uuid4

    trace_id = f"shortcut_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
    trace = {
        "trace_id": trace_id,
        "route_decision": case.route_decision or "direct_match",
        "status": "completed",
        "final_result": {
            "decision": case.final_decision,
            "answer_text": f"[历史相似案例] 决策：{case.final_decision}（来自 {case.workspace_run_id}）",
        },
        "failure_reason": None,
        "retrieval": {"matched_rule_id": None, "source_rule_ids": []},
        "step_results": [],
        "validator_results": [],
        "shortcut_from": case.workspace_run_id,
        "shortcut_score": case.score,
    }
    trace_dir.mkdir(parents=True, exist_ok=True)
    trace_path = trace_dir / f"{trace_id}.json"
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    return RuntimeResult(
        trace_id=trace_id,
        trace_path=trace_path,
        route_decision=case.route_decision or "direct_match",
        status="completed",
        final_result=trace["final_result"],
        matched_rule_id=None,
        failure_reason=None,
        source_rule_ids=[],
        missing_slots=[],
    )
