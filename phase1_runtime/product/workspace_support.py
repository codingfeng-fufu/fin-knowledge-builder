from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path
from typing import Any

from ..agents import build_super_agent_handoff, run_super_agent
from ..analysis import (
    fetch_multi_agent_exploration_result,
    poll_multi_agent_exploration_task,
    run_exploration_runtime,
    run_multi_agent_exploration,
    trigger_multi_agent_exploration,
)
from ..runtime_flags import runtime_rules_disabled
from ..skills import compile_rule_to_reusable_skill, materialize_skill_artifact, validate_skill_artifact
from .product_catalog import DECISION_TEXT_MAP, ROUTE_GUIDANCE_MAP


def _feedback_type(route_decision: str, status: str) -> str:
    if route_decision == "exploration":
        return "missed_rule"
    if route_decision == "needs_more_context":
        return "insufficient_context"
    if status != "completed" and route_decision == "rule_composable":
        return "composition_failure"
    return "workspace_observation"


def _feedback_rule_ids(route_decision: str, matched_rule_id: str | None, source_rule_ids: list[str]) -> list[str]:
    if source_rule_ids:
        return list(source_rule_ids)
    if matched_rule_id:
        return [matched_rule_id]
    return []


def _preferred_feedback_rule_ids(
    *,
    route_decision: str,
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    exploration_runtime: dict[str, Any] | None,
) -> list[str]:
    if exploration_runtime and exploration_runtime.get("recommended_rule_ids"):
        return [str(item) for item in exploration_runtime.get("recommended_rule_ids", []) if str(item)]
    return _feedback_rule_ids(route_decision, matched_rule_id, source_rule_ids)


def _validator_failures(trace_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in trace_payload.get("validator_results", []) if not item.get("ok", False)]


def _select_primary_binding(rule_bindings: list[Any]) -> Any | None:
    if not rule_bindings:
        return None
    ranked = sorted(
        rule_bindings,
        key=lambda item: (
            1 if item.binding_status == "bindable" else 0,
            item.binding_score,
            item.retrieval_score,
        ),
        reverse=True,
    )
    return ranked[0]


def _should_allow_shortcut(materials: list[dict[str, Any]]) -> bool:
    if runtime_rules_disabled():
        return False
    return not materials


def _grounded_retrieval_fact_keys(fact_sheet: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("fact_id"))
        for item in fact_sheet
        if item.get("status") in {"grounded", "assumed"} and item.get("fact_id")
    }


def _looks_like_machine_json(text: str) -> bool:
    stripped = text.strip()
    return (
        (stripped.startswith("{") and stripped.endswith("}"))
        or (stripped.startswith("[") and stripped.endswith("]"))
    )


def _super_agent_max_turns(question_text: str) -> int:
    lowered = question_text.lower()
    if any(token in lowered for token in ("python", "代码", "计算", "核算", "脚本")):
        return 14
    return 8


def _binding_status_text(binding_status: str) -> str:
    return {
        "bindable": "当前可直接回答",
        "partially_bindable": "还需补充信息",
        "unbindable": "当前不适用",
    }.get(binding_status, binding_status)


def _safe_reason_list(raw: str) -> list[str]:
    try:
        parsed = ast.literal_eval(raw)
    except Exception:
        return []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def _display_reasons(reasons: list[str]) -> list[str]:
    display: list[str] = []
    for reason in reasons:
        if reason.startswith("question_type_match="):
            values = _safe_reason_list(reason.split("=", 1)[1])
            if values:
                display.append(f"问题类型匹配：{' / '.join(values)}")
            continue
        if reason.startswith("intent_match="):
            values = _safe_reason_list(reason.split("=", 1)[1])
            if values:
                display.append(f"意图匹配：{' / '.join(values)}")
            continue
        if reason.startswith("document_type_match="):
            values = _safe_reason_list(reason.split("=", 1)[1])
            if values:
                display.append(f"文档类型匹配：{' / '.join(values)}")
            continue
        if reason.startswith("signal_hits="):
            display.append(f"命中 {reason.split('=', 1)[1]} 个规则信号")
            continue
        if reason.startswith("required_fact_hits="):
            display.append(f"命中 {reason.split('=', 1)[1]} 个必需字段")
            continue
        if reason.startswith("optional_fact_hits="):
            display.append(f"命中 {reason.split('=', 1)[1]} 个可选字段")
            continue
        if reason.startswith("lexical_overlap="):
            display.append(f"词项重合度：{reason.split('=', 1)[1]}")
            continue
        if reason.startswith("semantic_score="):
            display.append(f"语义匹配分：{reason.split('=', 1)[1]}")
            continue
    return display


def _binding_context_summary(binding: Any) -> str:
    if binding.binding_status == "bindable":
        if binding.satisfied_slots:
            return f"当前问题和文档已经足够支撑这条规则，已识别到：{'、'.join(binding.satisfied_slots)}。"
        return "当前问题和文档已经足够支撑这条规则。"
    if binding.binding_status == "partially_bindable":
        parts: list[str] = []
        if binding.satisfied_slots:
            parts.append(f"已识别：{'、'.join(binding.satisfied_slots)}")
        if binding.missing_slots:
            parts.append(f"仍缺少：{'、'.join(binding.missing_slots)}")
        if binding.assumed_slots:
            parts.append(f"当前仅能推定：{'、'.join(binding.assumed_slots)}")
        if binding.conflicting_slots:
            parts.append(f"存在冲突：{'、'.join(binding.conflicting_slots)}")
        return "；".join(parts) if parts else "当前只命中了部分条件，还不能稳定回答。"
    if binding.missing_slots:
        return f"这条规则当前不适用，缺少关键字段：{'、'.join(binding.missing_slots)}。"
    return "这条规则当前不适用。"


def _display_rule_binding(binding: Any, rule: Any) -> dict[str, Any]:
    payload = binding.to_dict()
    payload.update(
        {
            "rule_name": rule.name,
            "rule_kind_text": "场景答案模板" if rule.rule_kind == "composite" else "基础能力单元",
            "binding_status_text": _binding_status_text(binding.binding_status),
            "rule_scope": rule.applicability.scope,
            "rule_non_scope": rule.applicability.non_scope,
            "primary_goal": rule.steps[-1].goal if rule.steps else rule.applicability.scope,
            "step_count": len(rule.steps),
            "query_signals": list(rule.trigger.query_signals),
            "display_reasons": _display_reasons(list(binding.reasons)),
            "context_summary": _binding_context_summary(binding),
        }
    )
    return payload


def _display_decision_text(
    *,
    final_decision: str,
    final_answer: str,
    answer_engine: str,
    route_decision: str,
) -> str:
    label = DECISION_TEXT_MAP.get(final_decision, final_decision)
    if (
        answer_engine == "super_agent"
        and route_decision == "direct_match"
        and final_decision == "needs_review"
        and final_answer.strip()
        and not final_answer.strip().startswith("Stopped after reaching")
    ):
        return "已生成最终答案"
    if (
        answer_engine == "super_agent"
        and route_decision == "exploration"
        and final_answer.strip()
        and not final_answer.strip().startswith("Stopped after reaching")
    ):
        return "已生成探索性答案"
    if (
        route_decision == "exploration"
        and final_answer.strip()
        and not _looks_like_placeholder_exploration_answer(final_answer)
    ):
        return "已生成探索性答案"
    return label


_MISSING_INPUT_PATTERNS = [
    re.compile(r"missing required input: (?P<field>[A-Za-z0-9_]+)"),
    re.compile(r"compare_numeric requires numeric input for (?P<field>[A-Za-z0-9_]+), got None"),
]

_MISSING_SLOT_LABELS = {
    "days_to_maturity": "距离到期天数",
    "notice_threshold_days": "通知窗口天数",
    "contract_requires_notice": "合同是否要求通知借款人",
    "current_nav": "当前净值",
    "warning_threshold": "预警阈值",
    "contract_requires_warning": "合同是否要求风险提示",
}


def _missing_slots_from_failure_reason(failure_reason: str | None) -> list[str]:
    if not failure_reason:
        return []
    slots: list[str] = []
    for pattern in _MISSING_INPUT_PATTERNS:
        match = pattern.search(failure_reason)
        if match:
            field = str(match.group("field")).strip()
            if field and field not in slots:
                slots.append(field)
    return slots


def _present_missing_slots(missing_slots: list[str] | None) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for slot in missing_slots or []:
        items.append(
            {
                "slot_id": slot,
                "label": _MISSING_SLOT_LABELS.get(slot, slot),
            }
        )
    return items


def _build_exploration_links(exploration_runtime: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(exploration_runtime, dict):
        return None
    external_task = exploration_runtime.get("external_task")
    if not isinstance(external_task, dict):
        return None
    task_id = str(external_task.get("task_id") or "").strip()
    if not task_id:
        return None
    frontend_base = os.environ.get("PHASE1_EXPLORATION_FRONTEND_URL", "http://127.0.0.1:3000").rstrip("/")
    backend_base = os.environ.get("PHASE1_EXPLORATION_BACKEND_URL", "http://127.0.0.1:5001").rstrip("/")
    return {
        "task_id": task_id,
        "frontend_base_url": frontend_base,
        "backend_base_url": backend_base,
        "workbench_url": f"{frontend_base}/discovery",
        "report_url": f"{frontend_base}/discovery/report/{task_id}",
        "backend_task_url": f"{backend_base}/api/discovery/tasks/{task_id}",
        "backend_result_url": f"{backend_base}/api/discovery/tasks/{task_id}/result",
    }


def _looks_like_placeholder_exploration_answer(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return True
    placeholders = [
        "当前没有稳定规则可直接给出建议",
        "建议人工复核并记录反馈",
        "当前结果未完整生成",
    ]
    return any(item in normalized for item in placeholders)


def _clean_exploration_text(text: str) -> str:
    normalized = str(text or "")
    normalized = re.sub(r"\[(?:Input|INPUT|General Knowledge|GENERAL_KNOWLEDGE|Inference|INFERENCE|Input/Inference|Input/General Knowledge|Input/General Knowledge/Inference|General:.*?|Input:.*?|Inference:.*?)\]", "", normalized)
    normalized = re.sub(r"\s{2,}", " ", normalized)
    normalized = re.sub(r"\s+([，。；：])", r"\1", normalized)
    return normalized.strip()


def _build_exploration_provisional_answer(
    *,
    question_text: str,
    exploration_runtime: dict[str, Any] | None,
) -> str | None:
    if not isinstance(exploration_runtime, dict):
        return None

    candidate_drafts = list(exploration_runtime.get("candidate_rule_drafts") or [])
    external_result = exploration_runtime.get("external_result") or {}
    case_draft = exploration_runtime.get("case_draft") or {}
    if not candidate_drafts and not case_draft:
        return None

    primary = candidate_drafts[0] if candidate_drafts and isinstance(candidate_drafts[0], dict) else {}
    raw_rule_title = str(primary.get("rule_title") or primary.get("draft_type") or "候选规则").strip()
    rule_title = re.sub(r"\s*[（(]改造版[）)]\s*", "", raw_rule_title).strip() or raw_rule_title
    raw_rule_text = _clean_exploration_text(primary.get("rule_text") or "")
    summary = _clean_exploration_text(primary.get("summary") or case_draft.get("summary") or external_result.get("summary") or "")
    validation_reason = _clean_exploration_text(primary.get("validation_reason") or "")
    recommended_action = str(primary.get("recommended_action") or "").strip()
    open_questions = list(external_result.get("open_questions") or [])
    trigger_reason = str(exploration_runtime.get("trigger_reason") or "").strip()

    scenario_hint = "当前问题属于一个现有规则未稳定覆盖的新场景，需要先形成候选规则再决定是否正式接入。"
    if "公告" in question_text or "披露" in question_text:
        scenario_hint = "当前问题涉及对外披露措辞与误导风险控制，现有规则没有稳定覆盖这类语境。"
    if "业绩预告" in question_text:
        scenario_hint = "当前问题涉及业绩预告发布前的措辞审查与依据充分性，现有规则没有稳定覆盖这类语境。"

    if not rule_title or rule_title in {"candidate_atomic_rule_draft", "candidate_novel_rule_draft", "候选规则"}:
        if "业绩预告" in question_text:
            rule_title = "业绩预告披露前措辞与依据审查规则"
        elif "公告" in question_text or "披露" in question_text:
            rule_title = "对外披露模糊表述审查规则"
        else:
            rule_title = "新场景候选规则"

    if not summary:
        if "业绩预告" in question_text:
            summary = "当业绩预告说明存在乐观措辞但依据不足时，应先暂停发布、补充依据或下调表述强度，再决定是否对外披露。"
        elif "公告" in question_text or "披露" in question_text:
            summary = "当拟披露公告表述模糊且可能误导外部时，应先补充边界条件与风险提示，再决定是否发布。"
        else:
            summary = "当前问题未命中稳定规则，建议围绕当前语境形成一条新的候选规则。"

    if "未经复核不得直接对外发送" in raw_rule_text:
        concise_rule_text = "在涉及重大披露、业绩预告或对外承诺的文稿发布前，应先核实事实、时间、范围和承诺边界；如果表述可能误导外部，必须补充限制条件并完成复核，未经复核不得直接对外发送。"
    elif raw_rule_text:
        first_sentence = raw_rule_text.split("。")[0].strip()
        concise_rule_text = _clean_exploration_text(f"{first_sentence}。" if first_sentence else raw_rule_text)
    else:
        if "业绩预告" in question_text:
            concise_rule_text = "当业绩预告说明中出现显著增长、超预期等强表述，但缺少经审定的数据或明确的量化依据时，应立即暂停发布，补充依据或调整措辞，并增加风险提示，未经复核不得对外披露。"
        elif "公告" in question_text or "披露" in question_text:
            concise_rule_text = "当拟披露公告存在模糊表述、未确认事项或可能误导外部的措辞时，应先核实事实边界、补充限制条件和风险提示，未经复核不得直接对外发布。"
        else:
            concise_rule_text = "当新场景问题无法被现有规则覆盖时，应先形成候选规则并给出临时处理意见，待人工审核后再决定是否正式接入。"

    direct_advice = (
        f"针对“{question_text}”，当前更稳妥的处理方式是先按这条候选规则执行临时处理，再决定是否正式接入规则库。"
    )

    action_map = {
        "create_new_atomic_rule": "建议把这次处理逻辑沉淀为一条新的基础规则。",
        "create_or_patch_composite_rule": "建议把这次处理逻辑沉淀为一条新的复合规则或补丁规则。",
        "reuse_existing_method": "建议先按现有方法思路执行，再决定是否正式沉淀。",
    }
    action_line = action_map.get(recommended_action, "建议先形成临时处理意见，并继续人工审核。")

    lines = [
        "### 1. 临时处理意见",
        direct_advice,
        scenario_hint,
        action_line,
        "",
        "### 2. 当前候选规则",
        f"- 候选规则：{rule_title or '未命名候选规则'}",
    ]
    if summary:
        lines.append(f"- 适用摘要：{summary}")
    if concise_rule_text:
        lines.extend([
            "",
            "### 3. 规则内容预览",
            concise_rule_text,
        ])
    if validation_reason or open_questions:
        lines.extend(["", "### 4. 为什么还需要人工判断"])
        if validation_reason:
            lines.append(f"- 当前判断：{validation_reason}")
        for item in open_questions[:4]:
            lines.append(f"- 待确认：{_clean_exploration_text(item)}")
    if trigger_reason:
        lines.append(f"- 触发原因：{trigger_reason}")
    lines.extend([
        "",
        "### 5. 接入建议",
        "建议先把这条候选规则送入审核，而不是直接接入规则库。只有在量化标准、适用边界和审核责任补齐后，才适合成为正式规则。",
        "",
        "### 6. 当前状态",
        "这条规则还没有正式审核通过，因此这次答案属于探索性答案，只用于帮助判断这条候选规则是否值得接入。",
    ])
    return "\n".join(lines)


def _prepare_exploration_provisional_assets(
    *,
    exploration_runtime: dict[str, Any] | None,
    work_dir: str | Path,
    trace_id: str,
    effective_question: str,
    task_context: Any,
    parser_bundle: dict[str, Any],
    super_agent_max_turns: int,
    super_agent_backend: str,
    coding_agent_check_command: str | None,
    coding_agent_review_with_agent: bool,
    coding_agent_provider: str,
) -> dict[str, Any]:
    candidate_drafts = list((exploration_runtime or {}).get("candidate_rule_drafts") or [])
    if not candidate_drafts:
        return {
            "runtime_skill_spec_preview": None,
            "runtime_skill_artifact": None,
            "super_agent_handoff": None,
        }
    candidate = candidate_drafts[0] if isinstance(candidate_drafts[0], dict) else {}
    rule_title = str(candidate.get("rule_title") or candidate.get("draft_type") or "exploration_candidate")
    rule_text = str(candidate.get("rule_text") or candidate.get("summary") or "").strip()
    summary = str(candidate.get("summary") or (exploration_runtime or {}).get("case_draft", {}).get("summary") or "").strip()
    open_questions = list((exploration_runtime or {}).get("external_result", {}).get("open_questions") or [])

    skill_name = f"exploration-provisional-{trace_id}"
    root_path = Path(work_dir) / "runtime_skills" / trace_id / skill_name
    references_path = root_path / "references"
    references_path.mkdir(parents=True, exist_ok=True)
    open_question_lines = [f"- {item}" for item in open_questions[:6]] if open_questions else ["- none"]
    skill_md = "\n".join(
        [
            "---",
            f"name: {skill_name}",
            "description: Provisional method discovered from exploration. Use it to produce a tentative answer before formal rule admission.",
            "---",
            "",
            f"# {rule_title}",
            "",
            "## Role",
            "This is a provisional method draft generated by the exploration system, not a formally admitted rule.",
            "Use it to produce the best tentative answer to the user's question from the current context and evidence.",
            "",
            "## Priority",
            "1. Use the query-aware context packet first.",
            "2. Use the exploration candidate as a tentative solving strategy.",
            "3. If evidence is weak, still provide the most defensible tentative answer and make the uncertainty minimal and explicit.",
            "",
            "## Candidate Summary",
            summary or "(no summary)",
            "",
            "## Candidate Method",
            rule_text or "(no candidate rule text)",
            "",
            "## Open Questions",
            *open_question_lines,
            "",
            "## Final Answer Requirement",
            f"Answer the user's original question directly: {effective_question}",
            "The first sentence should be the shortest direct answer you can give.",
        ]
    )
    (root_path / "SKILL.md").write_text(skill_md, encoding="utf-8")
    (references_path / "exploration-runtime.json").write_text(
        json.dumps(exploration_runtime or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    runtime_skill_spec_preview = {
        "skill_name": skill_name,
        "description": "Exploration provisional method draft",
        "metadata": {
            "source_rule_id": None,
            "source": "exploration",
            "candidate_title": rule_title,
        },
        "skill_md": skill_md,
        "source_rule_id": rule_title,
        "skill_type": "exploration_provisional",
        "binding_status": "provisional",
    }
    runtime_skill_artifact = {
        "skill_name": skill_name,
        "title": rule_title,
        "description": summary or "Exploration provisional method draft",
        "source_rule_id": rule_title,
        "root_path": str(root_path),
        "skill_md_path": str(root_path / "SKILL.md"),
        "files": ["SKILL.md", "references/exploration-runtime.json"],
        "validation": validate_skill_artifact(root_path),
    }
    super_agent_handoff = build_super_agent_handoff(
        query=effective_question,
        skill_root=runtime_skill_artifact["root_path"],
        workspace_root=work_dir,
        task_context=task_context.to_dict(),
        context_packet=parser_bundle.get("context_packet", {}),
        max_turns=super_agent_max_turns,
        backend=super_agent_backend,
        coding_agent_check_command=coding_agent_check_command,
        coding_agent_review_with_agent=coding_agent_review_with_agent,
        coding_agent_provider=coding_agent_provider,
    )
    return {
        "runtime_skill_spec_preview": runtime_skill_spec_preview,
        "runtime_skill_artifact": runtime_skill_artifact,
        "super_agent_handoff": super_agent_handoff,
    }


def _build_workspace_solution_view(
    *,
    question_text: str,
    documents: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    parser_bundle: dict[str, Any],
    trace_payload: dict[str, Any],
    final_decision: str,
    final_answer: str,
    answer_engine: str,
    route_decision: str,
    runtime_result: Any,
    feedback_defaults: dict[str, Any],
) -> dict[str, Any]:
    candidate_rules = trace_payload.get("retrieval", {}).get("candidates", [])
    atomic_candidate_count = sum(1 for item in candidate_rules if item.get("rule_kind") == "atomic")
    composite_candidate_count = sum(1 for item in candidate_rules if item.get("rule_kind") != "atomic")
    return {
        "input": {
            "question_text": question_text,
            "documents": documents,
            "evidence_refs": evidence_packets,
            "evidence_count": len(evidence_packets),
        },
        "structured_understanding": {
            "question_types": parser_bundle["question_packet_preview"].get("question_types", []),
            "intents": parser_bundle["question_packet_preview"].get("intents", []),
            "document_types": parser_bundle["question_packet_preview"].get("document_types", []),
            "extracted_inputs": parser_bundle["question_packet_preview"].get("extracted_inputs", {}),
            "facts": parser_bundle["facts"],
            "fact_sheet": parser_bundle["fact_sheet"],
            "parser_status": parser_bundle["parser_status"],
        },
        "retrieval": {
            "candidate_rules": candidate_rules,
            "matched_rule_id": runtime_result.matched_rule_id,
            "source_rule_ids": list(runtime_result.source_rule_ids),
            "asset_counts": {
                "candidate_total": len(candidate_rules),
                "atomic_candidates": atomic_candidate_count,
                "composite_or_full_candidates": composite_candidate_count,
            },
        },
        "route": {
            "route_decision": route_decision,
            "composition_pattern": runtime_result.composition_pattern,
            "explanation": ROUTE_GUIDANCE_MAP.get(route_decision, route_decision),
        },
        "execution": {
            "timeline": trace_payload.get("step_results", []),
            "step_order": [item.get("step_id") for item in trace_payload.get("step_results", [])],
            "validator_failures": _validator_failures(trace_payload),
            "trace_id": runtime_result.trace_id,
            "trace_path": str(runtime_result.trace_path),
            "final_decision": final_decision,
            "final_answer": final_answer,
            "answer_engine": answer_engine,
        },
        "feedback": feedback_defaults,
    }


def _build_runtime_skill_artifact_view(
    artifact: Any,
    *,
    trace_id: str,
    work_dir: str | Path,
) -> dict[str, Any]:
    output_root = Path(work_dir) / "runtime_skills" / trace_id
    root_path = materialize_skill_artifact(artifact, output_root)
    file_map = artifact.file_map()
    validation = validate_skill_artifact(root_path)
    return {
        "skill_name": artifact.skill_name,
        "title": artifact.title,
        "description": artifact.description,
        "source_rule_id": artifact.metadata.get("source_rule_id"),
        "root_path": str(root_path),
        "skill_md_path": str(root_path / "SKILL.md"),
        "files": sorted(file_map.keys()),
        "validation": validation,
    }


def _prepare_super_agent_assets(
    *,
    primary_binding: Any | None,
    rule_by_id: dict[str, Any],
    task_context: Any,
    runtime_result: Any,
    work_dir: str | Path,
    effective_question: str,
    parser_bundle: dict[str, Any],
    super_agent_max_turns: int,
    super_agent_backend: str,
    coding_agent_check_command: str | None,
    coding_agent_review_with_agent: bool,
    coding_agent_provider: str,
) -> dict[str, Any]:
    runtime_skill_spec_preview = None
    runtime_skill_artifact = None
    super_agent_handoff = None

    if primary_binding is None or primary_binding.rule_id not in rule_by_id:
        return {
            "runtime_skill_spec_preview": runtime_skill_spec_preview,
            "runtime_skill_artifact": runtime_skill_artifact,
            "super_agent_handoff": super_agent_handoff,
        }

    artifact = compile_rule_to_reusable_skill(
        rule_by_id[primary_binding.rule_id],
        task_context,
        primary_binding,
        include_references=True,
    )
    runtime_skill_spec_preview = {
        "skill_name": artifact.skill_name,
        "description": artifact.description,
        "metadata": artifact.metadata,
        "skill_md": artifact.skill_md,
        "source_rule_id": artifact.metadata.get("source_rule_id"),
    }
    runtime_skill_artifact = _build_runtime_skill_artifact_view(
        artifact,
        trace_id=runtime_result.trace_id,
        work_dir=work_dir,
    )
    super_agent_handoff = build_super_agent_handoff(
        query=effective_question,
        skill_root=runtime_skill_artifact["root_path"],
        workspace_root=work_dir,
        task_context=task_context.to_dict(),
        context_packet=parser_bundle.get("context_packet", {}),
        max_turns=super_agent_max_turns,
        backend=super_agent_backend,
        coding_agent_check_command=coding_agent_check_command,
        coding_agent_review_with_agent=coding_agent_review_with_agent,
        coding_agent_provider=coding_agent_provider,
    )
    return {
        "runtime_skill_spec_preview": runtime_skill_spec_preview,
        "runtime_skill_artifact": runtime_skill_artifact,
        "super_agent_handoff": super_agent_handoff,
    }


def _resolve_workspace_answer(
    *,
    runtime_result: Any,
    route_decision: str,
    evidence_packets: list[dict[str, Any]],
) -> tuple[str, str, list[dict[str, Any]]]:
    if runtime_result.final_result is None:
        missing_slots = getattr(runtime_result, "missing_slots", None)
        inferred_missing_slots = _missing_slots_from_failure_reason(getattr(runtime_result, "failure_reason", None))
        if not missing_slots and inferred_missing_slots:
            missing_slots = inferred_missing_slots
        if route_decision == "needs_more_context":
            slots_hint = "、".join(missing_slots) if missing_slots else "部分关键字段"
            return (
                "needs_more_context",
                f"系统已识别到相关规则，但以下字段未能从文档中获取：{slots_hint}。请补充相关材料后重新提交。",
                evidence_packets,
            )
        if missing_slots:
            slots_hint = "、".join(missing_slots)
            return (
                "needs_more_context",
                f"系统已命中相关规则，但以下关键字段仍缺失：{slots_hint}。请补充材料后重新提交。",
                evidence_packets,
            )
        if route_decision == "exploration":
            return (
                "needs_review",
                "当前没有稳定规则可直接给出建议，系统已进入探索路径，建议人工复核并记录反馈。",
                evidence_packets,
            )
        return (
            "needs_review",
            "当前结果未完整生成，建议人工复核后再继续沉淀规则。",
            evidence_packets,
        )

    final_decision = str(runtime_result.final_result.get("decision", "needs_review"))
    final_answer = str(
        runtime_result.final_result.get("answer_text")
        or runtime_result.final_result.get("explanation")
        or "系统已生成结果。"
    )
    answer_evidence = runtime_result.final_result.get("evidence_refs")
    if isinstance(answer_evidence, list) and answer_evidence:
        return final_decision, final_answer, answer_evidence
    return final_decision, final_answer, evidence_packets


def _run_workspace_super_agent(
    *,
    runtime_skill_artifact: dict[str, Any] | None,
    super_agent_handoff: dict[str, Any] | None,
    run_live_super_agent: bool,
    kimi_client: Any | None,
    effective_question: str,
    work_dir: str | Path,
    task_context: Any,
    parser_bundle: dict[str, Any],
    super_agent_max_turns: int,
    effective_kimi_client: Any | None,
    super_agent_backend: str,
    coding_agent_check_command: str | None,
    coding_agent_review_with_agent: bool,
    coding_agent_provider: str,
    final_answer: str,
) -> tuple[str, str, dict[str, Any] | None]:
    super_agent_result = None
    answer_engine = "runtime"
    allow_live_super_agent = (
        run_live_super_agent
        or kimi_client is not None
        or os.environ.get("PHASE1_ENABLE_LIVE_SUPER_AGENT", "").lower() in {"1", "true", "yes"}
    )
    if runtime_skill_artifact is not None and super_agent_handoff is not None and allow_live_super_agent:
        try:
            super_agent_result = run_super_agent(
                query=effective_question,
                skill_root=runtime_skill_artifact["root_path"],
                workspace_root=work_dir,
                task_context=task_context.to_dict(),
                context_packet=parser_bundle.get("context_packet", {}),
                max_turns=super_agent_max_turns,
                kimi_client=effective_kimi_client,
                backend=super_agent_backend,
                coding_agent_check_command=coding_agent_check_command,
                coding_agent_review_with_agent=coding_agent_review_with_agent,
                coding_agent_provider=coding_agent_provider,
            )
            candidate_answer = str(super_agent_result.get("final_text") or "").strip()
            if candidate_answer and not _looks_like_machine_json(candidate_answer):
                final_answer = candidate_answer
                answer_engine = "super_agent"
        except Exception as exc:
            super_agent_result = {
                "error": str(exc),
                "query": effective_question,
                "skill_root": runtime_skill_artifact["root_path"],
            }
    elif runtime_skill_artifact is not None and super_agent_handoff is not None:
        super_agent_result = {
            "status": "not_run",
            "reason": "live_super_agent_disabled",
            "query": effective_question,
            "skill_root": runtime_skill_artifact["root_path"],
        }
    return final_answer, answer_engine, super_agent_result


def _resolve_workspace_exploration_runtime(
    *,
    trace_id: str,
    route_decision: str,
    runtime_status: str,
    scenario_id: str,
    effective_question: str,
    final_decision: str,
    failure_reason: str | None,
    parser_bundle: dict[str, Any],
    documents: list[dict[str, Any]],
    document_chunks: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    rules: list[Any],
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    fallback_rule_ids: list[str],
    exploration_backend: str,
    exploration_use_llm: bool,
    exploration_mode: str,
    block_until_complete: bool = False,
) -> dict[str, Any] | None:
    if route_decision != "exploration" and not (route_decision == "rule_composable" and runtime_status != "completed"):
        return None
    if exploration_backend != "multi_agent_exploration":
        return run_exploration_runtime(
            scenario_id=scenario_id,
            question_text=effective_question,
            route_decision=route_decision,
            runtime_status=runtime_status,
            final_decision=final_decision,
            failure_reason=failure_reason,
            parser_status=parser_bundle["parser_status"],
            missing_fact_keys=parser_bundle["missing_fact_keys"],
            fact_sheet=parser_bundle["fact_sheet"],
            documents=documents,
            matched_rule_id=matched_rule_id,
            source_rule_ids=source_rule_ids,
            fallback_rule_ids=fallback_rule_ids,
        )

    context_summary = str((parser_bundle.get("context_packet") or {}).get("context_summary") or "")

    if block_until_complete:
        try:
            return run_multi_agent_exploration(
                scenario_id=scenario_id,
                question_text=effective_question,
                route_decision=route_decision,
                runtime_status=runtime_status,
                final_decision=final_decision,
                failure_reason=failure_reason,
                parser_status=parser_bundle["parser_status"],
                missing_fact_keys=parser_bundle["missing_fact_keys"],
                fact_sheet=parser_bundle["fact_sheet"],
                documents=documents,
                document_chunks=document_chunks,
                evidence_packets=evidence_packets,
                rules=rules,
                matched_rule_id=matched_rule_id,
                source_rule_ids=source_rule_ids,
                fallback_rule_ids=fallback_rule_ids,
                context_summary=context_summary,
                trace_id=trace_id,
                use_llm=exploration_use_llm,
                discovery_mode=exploration_mode,
                timeout_seconds=600 if exploration_use_llm else 120,
            )
        except Exception as exc:
            payload = run_exploration_runtime(
                scenario_id=scenario_id,
                question_text=effective_question,
                route_decision=route_decision,
                runtime_status=runtime_status,
                final_decision=final_decision,
                failure_reason=failure_reason,
                parser_status=parser_bundle["parser_status"],
                missing_fact_keys=parser_bundle["missing_fact_keys"],
                fact_sheet=parser_bundle["fact_sheet"],
                documents=documents,
                matched_rule_id=matched_rule_id,
                source_rule_ids=source_rule_ids,
                fallback_rule_ids=fallback_rule_ids,
            )
            payload["external_backend"] = "multi_agent_exploration"
            payload["external_backend_error"] = str(exc)
            return payload

    # Non-blocking: trigger exploration and return with pending status
    try:
        trigger_result = trigger_multi_agent_exploration(
            scenario_id=scenario_id,
            question_text=effective_question,
            route_decision=route_decision,
            runtime_status=runtime_status,
            final_decision=final_decision,
            failure_reason=failure_reason,
            parser_status=parser_bundle["parser_status"],
            missing_fact_keys=parser_bundle["missing_fact_keys"],
            fact_sheet=parser_bundle["fact_sheet"],
            documents=documents,
            document_chunks=document_chunks,
            evidence_packets=evidence_packets,
            rules=rules,
            matched_rule_id=matched_rule_id,
            source_rule_ids=source_rule_ids,
            fallback_rule_ids=fallback_rule_ids,
            context_summary=context_summary,
            use_llm=exploration_use_llm,
            discovery_mode=exploration_mode,
        )
        return {
            "status": "exploration_pending",
            "external_backend": "multi_agent_exploration",
            "external_task": {"task_id": trigger_result["task_id"]},
            "trigger_reason": failure_reason or "no_direct_or_composable_rule",
            "candidate_rule_drafts": [],
            "recommended_feedback_type": "missed_rule",
            "recommended_rule_ids": list(source_rule_ids or fallback_rule_ids[:1]),
        }
    except Exception as exc:
        payload = run_exploration_runtime(
            scenario_id=scenario_id,
            question_text=effective_question,
            route_decision=route_decision,
            runtime_status=runtime_status,
            final_decision=final_decision,
            failure_reason=failure_reason,
            parser_status=parser_bundle["parser_status"],
            missing_fact_keys=parser_bundle["missing_fact_keys"],
            fact_sheet=parser_bundle["fact_sheet"],
            documents=documents,
            matched_rule_id=matched_rule_id,
            source_rule_ids=source_rule_ids,
            fallback_rule_ids=fallback_rule_ids,
        )
        payload["external_backend"] = "multi_agent_exploration"
        payload["external_backend_error"] = str(exc)
        return payload


def _complete_workspace_exploration_runtime(
    task_id: str,
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
    """Fetch a completed exploration task result and map it to the exploration_runtime format."""
    return fetch_multi_agent_exploration_result(
        task_id=task_id,
        scenario_id=scenario_id,
        question_text=question_text,
        route_decision=route_decision,
        runtime_status=runtime_status,
        final_decision=final_decision,
        failure_reason=failure_reason,
        parser_status=parser_status,
        missing_fact_keys=missing_fact_keys,
        fact_sheet=fact_sheet,
        documents=documents,
        matched_rule_id=matched_rule_id,
        source_rule_ids=source_rule_ids,
        fallback_rule_ids=fallback_rule_ids,
    )


def _build_workspace_feedback_defaults(
    *,
    runtime_result: Any,
    final_decision: str,
    final_answer: str,
    answer_engine: str,
    parser_bundle: dict[str, Any],
    scenario_id: str,
    exploration_runtime: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "trace_id": runtime_result.trace_id,
        "case_id": None,
        "route_decision": runtime_result.route_decision,
        "feedback_type": _feedback_type(runtime_result.route_decision, runtime_result.status),
        "rule_ids": _preferred_feedback_rule_ids(
            route_decision=runtime_result.route_decision,
            matched_rule_id=runtime_result.matched_rule_id,
            source_rule_ids=list(runtime_result.source_rule_ids),
            exploration_runtime=exploration_runtime,
        ),
        "payload": {
            "entry": "workspace",
            "scenario_id": scenario_id,
            "runtime_status": runtime_result.status,
            "final_decision": final_decision,
            "final_answer": final_answer,
            "answer_engine": answer_engine,
            "parser_status": parser_bundle["parser_status"],
            "missing_fact_keys": parser_bundle["missing_fact_keys"],
        },
    }


def _summarize_uploaded_materials(
    *,
    normalized_materials: list[dict[str, Any]],
    parsed_materials: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "char_count": parsed_materials[index].get("char_count", 0),
            "line_count": parsed_materials[index].get("line_count", 0),
            "parse_status": parsed_materials[index].get("parse_status"),
            "source_type": parsed_materials[index].get("source_type"),
            "size": item.get("size"),
        }
        for index, item in enumerate(normalized_materials)
    ]


def _build_workspace_feedback_payload(
    *,
    feedback_defaults: dict[str, Any],
    effective_question: str,
    parser_bundle: dict[str, Any],
    task_context: Any,
    document_parse_result: dict[str, Any],
    exploration_runtime: dict[str, Any] | None,
    runtime_result: Any,
    trace_payload: dict[str, Any],
    embedding_backend: dict[str, Any],
    runtime_skill_spec_preview: dict[str, Any] | None,
    answer_engine: str,
) -> dict[str, Any]:
    return {
        **feedback_defaults["payload"],
        "question_text": effective_question,
        "question_packet_preview": parser_bundle["question_packet_preview"],
        "document_packet_preview": parser_bundle["document_packet_preview"],
        "context_packet": parser_bundle.get("context_packet", {}),
        "fact_sheet": parser_bundle["fact_sheet"],
        "task_context": task_context.to_dict(),
        "unsupported_files": document_parse_result["unsupported_files"],
        "exploration_runtime": exploration_runtime,
        "recommended_action": (
            ((exploration_runtime or {}).get("candidate_rule_drafts") or [{}])[0].get("recommended_action")
            if exploration_runtime
            else None
        ),
        "matched_rule_id": runtime_result.matched_rule_id,
        "failure_reason": trace_payload.get("failure_reason"),
        "embedding_backend": embedding_backend,
        "retrieval_diagnostics": (trace_payload.get("retrieval", {}) or {}).get("diagnostics", {}),
        "runtime_skill_spec_preview": {} if runtime_skill_spec_preview is None else dict(runtime_skill_spec_preview),
        "answer_engine": answer_engine,
    }
