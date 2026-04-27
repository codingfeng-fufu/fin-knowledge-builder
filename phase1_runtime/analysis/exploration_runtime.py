from __future__ import annotations

from typing import Any
from uuid import uuid4


def _trigger_reason(route_decision: str, runtime_status: str, failure_reason: str | None, final_decision: str) -> str:
    if failure_reason:
        return failure_reason
    if route_decision == "rule_composable" and runtime_status != "completed":
        return "composition_failed"
    if route_decision == "exploration":
        return "no_direct_or_composable_rule"
    if final_decision == "needs_review":
        return "low_confidence"
    return "unclassified_gap"


def _case_draft(
    *,
    exploration_trace_id: str,
    scenario_id: str,
    question_text: str,
    route_decision: str,
    trigger_reason: str,
    parser_status: str,
    missing_fact_keys: list[str],
    fact_sheet: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "case_draft_id": f"case_draft_{exploration_trace_id}",
        "scenario_id": scenario_id,
        "question_text": question_text,
        "route_decision": route_decision,
        "trigger_reason": trigger_reason,
        "parser_status": parser_status,
        "missing_fact_keys": list(missing_fact_keys),
        "fact_count": len(fact_sheet),
        "document_count": len(documents),
        "needs_human_review": True,
        "summary": f"{scenario_id} 在 {trigger_reason} 条件下进入 Exploration Runtime，已生成 case draft。",
    }


def _candidate_rule_drafts(
    *,
    scenario_id: str,
    route_decision: str,
    source_rule_ids: list[str],
    matched_rule_id: str | None,
    fallback_rule_ids: list[str],
    missing_fact_keys: list[str],
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if route_decision == "rule_composable" and source_rule_ids:
        suggestions.append(
            {
                "draft_type": "candidate_composite_rule_draft",
                "recommended_action": "create_or_patch_composite_rule",
                "based_on_rule_ids": list(source_rule_ids),
                "summary": "组合链已经显式出现，适合沉淀为正式 composite rule。",
            }
        )
        return suggestions

    base_rule_ids: list[str] = []
    if matched_rule_id:
        base_rule_ids = [matched_rule_id]
    elif fallback_rule_ids:
        base_rule_ids = [fallback_rule_ids[0]]

    suggestions.append(
        {
            "draft_type": "candidate_atomic_rule_draft",
            "recommended_action": "create_new_atomic_rule",
            "based_on_rule_ids": base_rule_ids,
            "missing_fact_keys": list(missing_fact_keys),
            "summary": "当前问题未命中稳定规则，建议从该 case 中抽取新的 atomic rule 候选。",
        }
    )
    return suggestions


def _evidence_pattern_suggestions(missing_fact_keys: list[str], fact_sheet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for fact_key in missing_fact_keys:
        suggestions.append(
            {
                "pattern_type": "fact_extraction",
                "fact_key": fact_key,
                "summary": f"需要为 {fact_key} 增加更稳定的文档事实抽取模式。",
            }
        )
    if not suggestions and fact_sheet:
        suggestions.append(
            {
                "pattern_type": "evidence_locator",
                "fact_key": fact_sheet[0]["fact_id"],
                "summary": "已有事实层可用，但仍建议补强 evidence locator 模式。",
            }
        )
    return suggestions


def _validator_pattern_suggestions(route_decision: str, final_decision: str, runtime_status: str) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if route_decision == "rule_composable" and runtime_status != "completed":
        suggestions.append(
            {
                "pattern_type": "composition_guard",
                "summary": "组合链失败，建议增加 composition validator 或 binding guard。",
            }
        )
    if final_decision == "needs_review":
        suggestions.append(
            {
                "pattern_type": "review_gate",
                "summary": "当前结果落到 needs_review，建议补充更明确的 validator pattern。",
            }
        )
    return suggestions


def run_exploration_runtime(
    *,
    scenario_id: str,
    question_text: str,
    route_decision: str,
    runtime_status: str,
    final_decision: str,
    failure_reason: str | None,
    parser_status: str,
    missing_fact_keys: list[str],
    fact_sheet: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    fallback_rule_ids: list[str],
) -> dict[str, Any]:
    trigger_reason = _trigger_reason(route_decision, runtime_status, failure_reason, final_decision)
    exploration_trace_id = f"explore_{uuid4().hex[:12]}"
    candidate_drafts = _candidate_rule_drafts(
        scenario_id=scenario_id,
        route_decision=route_decision,
        source_rule_ids=source_rule_ids,
        matched_rule_id=matched_rule_id,
        fallback_rule_ids=fallback_rule_ids,
        missing_fact_keys=missing_fact_keys,
    )
    return {
        "exploration_trace_id": exploration_trace_id,
        "mode": "controlled_deterministic_mvp",
        "trigger_reason": trigger_reason,
        "route_entry": route_decision,
        "case_draft": _case_draft(
            exploration_trace_id=exploration_trace_id,
            scenario_id=scenario_id,
            question_text=question_text,
            route_decision=route_decision,
            trigger_reason=trigger_reason,
            parser_status=parser_status,
            missing_fact_keys=missing_fact_keys,
            fact_sheet=fact_sheet,
            documents=documents,
        ),
        "candidate_rule_drafts": candidate_drafts,
        "evidence_pattern_suggestions": _evidence_pattern_suggestions(missing_fact_keys, fact_sheet),
        "validator_pattern_suggestions": _validator_pattern_suggestions(route_decision, final_decision, runtime_status),
        "recommended_feedback_type": "composition_failure" if route_decision == "rule_composable" else "missed_rule",
        "recommended_rule_ids": list(source_rule_ids) or ([matched_rule_id] if matched_rule_id else list(fallback_rule_ids[:1])),
    }
