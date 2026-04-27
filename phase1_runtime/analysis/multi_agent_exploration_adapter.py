from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..schema import Rule


_EXTERNAL_REPO_ROOT = Path(__file__).resolve().parents[2] / "muti_agent_exploration"
_EXTERNAL_BACKEND_ROOT = _EXTERNAL_REPO_ROOT / "backend"
_EXTERNAL_BACKEND_PYTHON = _EXTERNAL_BACKEND_ROOT / ".venv" / "bin" / "python"
_RUNNER_SCRIPT = Path(__file__).resolve().with_name("external_rule_discovery_runner.py")
_DISCOVERY_BACKEND_URL = "http://127.0.0.1:5001"
_DISCOVERY_API_TIMEOUT = 30


class MultiAgentExplorationError(RuntimeError):
    pass


def _rule_payload(rule: Rule, priority: int) -> dict[str, Any]:
    conditions = list(rule.trigger.query_signals)
    conditions.extend(field.key for field in rule.inputs.required)
    content_parts = [
        rule.name,
        rule.applicability.scope,
        "；".join(step.goal for step in rule.steps[:3]),
    ]
    return {
        "rule_id": rule.rule_id,
        "title": rule.name,
        "content": "\n".join(part for part in content_parts if part),
        "conditions": [item for item in conditions if item],
        "exceptions": [rule.applicability.non_scope] if rule.applicability.non_scope else [],
        "priority": priority,
        "source": "phase1_runtime",
        "tags": [rule.rule_family, rule.rule_kind],
        "metadata": {
            "rule_family": rule.rule_family,
            "rule_kind": rule.rule_kind,
            "question_types": list(rule.trigger.question_types),
            "intents": list(rule.trigger.intents),
            "must_include": list(rule.outputs.must_include),
        },
    }


def _placeholder_rule_payload() -> dict[str, Any]:
    return {
        "rule_id": "phase1.no_active_runtime_rules",
        "title": "No Active Runtime Rules",
        "content": (
            "The main system currently has no active runtime rules enabled. "
            "Treat this task as a from-scratch discovery problem driven by query and document evidence."
        ),
        "conditions": [],
        "exceptions": [],
        "priority": 1,
        "source": "phase1_runtime",
        "tags": ["system", "no_active_rules"],
        "metadata": {
            "rule_family": "system",
            "rule_kind": "placeholder",
            "question_types": [],
            "intents": [],
            "must_include": [],
        },
    }


def _group_document_chunks(
    *,
    documents: list[dict[str, Any]],
    document_chunks: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    question_text: str,
    context_summary: str,
) -> list[dict[str, Any]]:
    title_by_id = {
        str(item.get("doc_id")): str(item.get("title") or item.get("doc_id") or "document")
        for item in documents
    }
    grouped: dict[str, list[str]] = {}
    for chunk in document_chunks:
        doc_id = str(chunk.get("doc_id") or "document")
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        grouped.setdefault(doc_id, []).append(text)

    if not grouped:
        for item in evidence_packets:
            doc_id = str(item.get("doc_id") or "evidence")
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            grouped.setdefault(doc_id, []).append(text)

    if not grouped:
        grouped["synthetic_context"] = [question_text, context_summary]
        title_by_id.setdefault("synthetic_context", "当前问题上下文")

    payloads: list[dict[str, Any]] = []
    for doc_id, parts in grouped.items():
        merged = "\n".join(part for part in parts if part).strip()
        if not merged:
            continue
        payloads.append(
            {
                "title": title_by_id.get(doc_id, doc_id),
                "content": merged,
                "metadata": {
                    "doc_id": doc_id,
                    "source": "phase1_runtime",
                },
            }
        )
    return payloads


def _candidate_action(candidate_type: str) -> tuple[str, str]:
    if candidate_type == "exact_reuse":
        return "candidate_reuse_rule", "reuse_existing_method"
    if candidate_type == "adapted_rule":
        return "candidate_adapted_rule_draft", "create_or_patch_composite_rule"
    return "candidate_novel_rule_draft", "create_new_atomic_rule"


def _candidate_rule_drafts(result: dict[str, Any], fallback_rule_ids: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for candidate in result.get("candidate_rules", []):
        candidate_type = str(candidate.get("candidate_type") or "novel_rule")
        draft_type, action = _candidate_action(candidate_type)
        based_on = list(candidate.get("derived_from") or [])
        if not based_on and candidate.get("rule_id"):
            based_on = [str(candidate["rule_id"])]
        if not based_on:
            based_on = list(fallback_rule_ids[:1])
        items.append(
            {
                "draft_type": draft_type,
                "recommended_action": action,
                "based_on_rule_ids": based_on,
                "summary": candidate.get("why_applicable")
                or candidate.get("adaptation_note")
                or candidate.get("validation_reason")
                or result.get("summary", ""),
                "candidate_type": candidate_type,
                "rule_title": candidate.get("rule_title"),
                "rule_text": candidate.get("rule_text"),
                "confidence": candidate.get("confidence"),
                "grounding_score": candidate.get("grounding_score"),
                "speculation_score": candidate.get("speculation_score"),
                "validation_status": candidate.get("validation_status"),
                "validation_reason": candidate.get("validation_reason"),
                "knowledge_sources": list(candidate.get("knowledge_sources") or []),
                "evidence_refs": list(candidate.get("evidence_refs") or []),
            }
        )
    return items


def _evidence_pattern_suggestions(result: dict[str, Any], missing_fact_keys: list[str]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for fact_key in missing_fact_keys:
        suggestions.append(
            {
                "pattern_type": "fact_extraction",
                "fact_key": fact_key,
                "summary": f"当前仍需要为 {fact_key} 补强更稳定的证据抽取方式。",
            }
        )
    for item in result.get("open_questions", [])[:3]:
        suggestions.append(
            {
                "pattern_type": "open_question",
                "fact_key": "open_question",
                "summary": str(item),
            }
        )
    return suggestions


def _validator_pattern_suggestions(result: dict[str, Any]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    if result.get("need_human_review"):
        suggestions.append(
            {
                "pattern_type": "human_review_gate",
                "summary": "当前候选解法仍需人工复核，建议增加更明确的审核或验证模式。",
            }
        )
    for candidate in result.get("candidate_rules", []):
        if str(candidate.get("validation_status")) in {"weakly_supported", "provisionally_supported"}:
            suggestions.append(
                {
                    "pattern_type": "validation_strengthening",
                    "summary": f"候选“{candidate.get('rule_title') or candidate.get('candidate_id')}”仍需补强验证依据。",
                }
            )
    return suggestions


def _case_draft(
    *,
    task_id: str,
    scenario_id: str,
    question_text: str,
    route_decision: str,
    trigger_reason: str,
    parser_status: str,
    missing_fact_keys: list[str],
    fact_sheet: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "case_draft_id": f"case_draft_{task_id}",
        "scenario_id": scenario_id,
        "question_text": question_text,
        "route_decision": route_decision,
        "trigger_reason": trigger_reason,
        "parser_status": parser_status,
        "missing_fact_keys": list(missing_fact_keys),
        "fact_count": len(fact_sheet),
        "document_count": len(documents),
        "needs_human_review": bool(result.get("need_human_review", False)),
        "summary": result.get("summary") or "多智能体探索系统已生成一份候选解法摘要。",
    }


def _map_runner_payload(
    *,
    runner_payload: dict[str, Any],
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
    task = runner_payload.get("task", {})
    result = runner_payload.get("result", {})
    trigger_reason = failure_reason or (
        "composition_failed"
        if route_decision == "rule_composable" and runtime_status != "completed"
        else "no_direct_or_composable_rule"
        if route_decision == "exploration"
        else "low_confidence"
        if final_decision == "needs_review"
        else "unclassified_gap"
    )
    candidate_drafts = _candidate_rule_drafts(result, fallback_rule_ids=fallback_rule_ids)
    recommended_rule_ids = list(source_rule_ids)
    if not recommended_rule_ids and matched_rule_id:
        recommended_rule_ids = [matched_rule_id]
    if not recommended_rule_ids and candidate_drafts:
        recommended_rule_ids = list(candidate_drafts[0].get("based_on_rule_ids") or [])
    if not recommended_rule_ids:
        recommended_rule_ids = list(fallback_rule_ids[:1])

    return {
        "exploration_trace_id": task.get("task_id") or f"explore_{uuid4().hex[:12]}",
        "mode": f"multi_agent_exploration_{result.get('discovery_mode') or task.get('discovery_mode') or 'grounded'}",
        "trigger_reason": trigger_reason,
        "route_entry": route_decision,
        "case_draft": _case_draft(
            task_id=task.get("task_id") or uuid4().hex[:12],
            scenario_id=scenario_id,
            question_text=question_text,
            route_decision=route_decision,
            trigger_reason=trigger_reason,
            parser_status=parser_status,
            missing_fact_keys=missing_fact_keys,
            fact_sheet=fact_sheet,
            documents=documents,
            result=result,
        ),
        "candidate_rule_drafts": candidate_drafts,
        "evidence_pattern_suggestions": _evidence_pattern_suggestions(result, missing_fact_keys),
        "validator_pattern_suggestions": _validator_pattern_suggestions(result),
        "recommended_feedback_type": "composition_failure" if route_decision == "rule_composable" else "missed_rule",
        "recommended_rule_ids": recommended_rule_ids,
        "external_result": result,
        "external_task": task,
        "external_stages": list(runner_payload.get("stages", [])),
        "external_logs": list(runner_payload.get("logs", []))[-12:],
    }


def _discovery_request(method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an HTTP request to the discovery backend and return the data field."""
    url = f"{_DISCOVERY_BACKEND_URL}{path}"
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_DISCOVERY_API_TIMEOUT) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if not result.get("success", False):
                raise MultiAgentExplorationError(
                    f"discovery backend {method} {path} failed: {result.get('error', 'unknown')}"
                )
            return result["data"]
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        raise MultiAgentExplorationError(f"discovery backend {method} {path} returned {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise MultiAgentExplorationError(
            f"discovery backend unreachable ({exc.reason}): {_DISCOVERY_BACKEND_URL}{path}"
        ) from exc


def trigger_multi_agent_exploration(
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
    document_chunks: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    rules: list[Rule],
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    fallback_rule_ids: list[str],
    context_summary: str,
    use_llm: bool = True,
    discovery_mode: str = "emergent",
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Trigger multi-agent exploration via HTTP to the discovery backend (non-blocking).

    Returns immediately with the task_id; the discovery backend runs the task asynchronously.
    """
    # 1. Import rules
    raw_rules = [_rule_payload(rule, priority=max(1, 100 - index)) for index, rule in enumerate(rules)]
    if not raw_rules:
        raw_rules = [_placeholder_rule_payload()]

    rule_set_name = f"phase1_{scenario_id}_{uuid4().hex[:8]}"
    rule_set = _discovery_request("POST", "/api/discovery/rule-sets/import", {
        "name": rule_set_name,
        "description": f"Imported from phase1_runtime scenario={scenario_id}",
        "rules": raw_rules,
    })
    rule_set_id = rule_set["rule_set_id"]

    # 2. Import documents
    raw_documents = _group_document_chunks(
        documents=documents,
        document_chunks=document_chunks,
        evidence_packets=evidence_packets,
        question_text=question_text,
        context_summary=context_summary,
    )
    document_set_id: str | None = None
    if raw_documents:
        doc_set_name = f"phase1_docs_{scenario_id}_{uuid4().hex[:8]}"
        doc_import = _discovery_request("POST", "/api/discovery/documents/import", {
            "name": doc_set_name,
            "description": f"Workspace materials for scenario={scenario_id}",
            "documents": raw_documents,
            "chunk_size": 800,
            "overlap": 120,
        })
        document_set_id = (doc_import.get("document_set") or {}).get("document_set_id")

    # 3. Create discovery task (runs async in discovery backend)
    trigger_reason = failure_reason or (
        "composition_failed"
        if route_decision == "rule_composable" and runtime_status != "completed"
        else "no_direct_or_composable_rule"
        if route_decision == "exploration"
        else "low_confidence"
        if final_decision == "needs_review"
        else "unclassified_gap"
    )
    context_parts = [
        context_summary,
        f"trigger_reason={trigger_reason}",
        f"missing_fact_keys={','.join(missing_fact_keys)}" if missing_fact_keys else "",
    ]
    context_str = "\n".join(part for part in context_parts if part)

    task = _discovery_request("POST", "/api/discovery/tasks/discover-rule", {
        "query": question_text,
        "context": context_str,
        "rule_set_id": rule_set_id,
        "document_set_id": document_set_id,
        "use_llm": bool(use_llm),
        "discovery_mode": discovery_mode,
        "metadata": {
            "source": "phase1_runtime",
            "scenario_id": scenario_id,
            "route_decision": route_decision,
            "phase1_trace_id": "",
        },
        "deduplicate": False,
    })

    return {
        "task_id": task["task_id"],
        "status": "pending",
        "rule_set_id": rule_set_id,
        "document_set_id": document_set_id,
    }


def poll_multi_agent_exploration_task(task_id: str) -> dict[str, Any]:
    """Check the current status of a multi-agent exploration task.

    Returns dict with status, progress, current_stage and completion flags.
    """
    task = _discovery_request("GET", f"/api/discovery/tasks/{task_id}")
    return {
        "task_id": task["task_id"],
        "status": task["status"],
        "progress": task.get("progress", 0),
        "current_stage": task.get("current_stage", ""),
        "completed": task["status"] in {"completed", "need_human_review", "insufficient_evidence"},
        "failed": task["status"] in {"failed", "timed_out", "cancelled"},
    }


def fetch_multi_agent_exploration_result(
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
    """Fetch the completed exploration task result and map to the exploration_runtime format."""
    task_info = poll_multi_agent_exploration_task(task_id)
    if task_info["failed"]:
        raise MultiAgentExplorationError(
            f"exploration task {task_id} ended with status: {task_info['status']}"
        )
    if not task_info["completed"]:
        raise MultiAgentExplorationError(
            f"exploration task {task_id} is not yet completed (status: {task_info['status']})"
        )

    result = _discovery_request("GET", f"/api/discovery/tasks/{task_id}/result")
    stages = _discovery_request("GET", f"/api/discovery/tasks/{task_id}/stages")
    logs = _discovery_request("GET", f"/api/discovery/tasks/{task_id}/logs")

    runner_payload = {
        "success": True,
        "task": {"task_id": task_id, "status": task_info["status"], "discovery_mode": None},
        "result": result,
        "stages": stages.get("stages", []),
        "logs": logs.get("logs", []),
    }
    return _map_runner_payload(
        runner_payload=runner_payload,
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


def run_multi_agent_exploration(
    *,
    trace_id: str,
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
    document_chunks: list[dict[str, Any]],
    evidence_packets: list[dict[str, Any]],
    rules: list[Rule],
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    fallback_rule_ids: list[str],
    context_summary: str,
    use_llm: bool = True,
    discovery_mode: str = "emergent",
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    if not _EXTERNAL_BACKEND_PYTHON.exists():
        raise MultiAgentExplorationError(
            f"external exploration python not found: {_EXTERNAL_BACKEND_PYTHON}"
        )
    if not _RUNNER_SCRIPT.exists():
        raise MultiAgentExplorationError(f"runner script not found: {_RUNNER_SCRIPT}")

    raw_rules = [_rule_payload(rule, priority=max(1, 100 - index)) for index, rule in enumerate(rules)]
    if not raw_rules:
        raw_rules = [_placeholder_rule_payload()]
    raw_documents = _group_document_chunks(
        documents=documents,
        document_chunks=document_chunks,
        evidence_packets=evidence_packets,
        question_text=question_text,
        context_summary=context_summary,
    )
    trigger_reason = failure_reason or (
        "composition_failed"
        if route_decision == "rule_composable" and runtime_status != "completed"
        else "no_direct_or_composable_rule"
        if route_decision == "exploration"
        else "low_confidence"
        if final_decision == "needs_review"
        else "unclassified_gap"
    )

    payload = {
        "backend_root": str(_EXTERNAL_BACKEND_ROOT.resolve()),
        "query": question_text,
        "context": "\n".join(
            part
            for part in [
                context_summary,
                f"trigger_reason={trigger_reason}",
                f"missing_fact_keys={','.join(missing_fact_keys)}" if missing_fact_keys else "",
            ]
            if part
        ),
        "rules": raw_rules,
        "documents": raw_documents,
        "rule_set_name": f"phase1_{scenario_id}_{uuid4().hex[:8]}",
        "rule_set_description": f"Imported from phase1_runtime scenario={scenario_id}",
        "document_set_name": f"phase1_docs_{scenario_id}_{uuid4().hex[:8]}",
        "document_set_description": f"Workspace materials for scenario={scenario_id}",
        "use_llm": bool(use_llm),
        "discovery_mode": discovery_mode,
        "timeout_seconds": int(timeout_seconds),
        "metadata": {
            "source": "phase1_runtime",
            "scenario_id": scenario_id,
            "route_decision": route_decision,
            "phase1_trace_id": trace_id,
        },
    }
    completed = subprocess.run(
        [str(_EXTERNAL_BACKEND_PYTHON), str(_RUNNER_SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(_EXTERNAL_BACKEND_ROOT),
        timeout=max(5, int(timeout_seconds) + 10),
        check=False,
    )
    if completed.returncode != 0:
        raise MultiAgentExplorationError(
            f"multi-agent exploration failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )

    try:
        runner_payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise MultiAgentExplorationError(
            f"invalid exploration runner output: {completed.stdout[:400]}"
        ) from exc

    if not runner_payload.get("success", False):
        raise MultiAgentExplorationError(f"exploration runner returned failure: {runner_payload}")
    return _map_runner_payload(
        runner_payload=runner_payload,
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


def rerun_multi_agent_exploration(
    *,
    previous_exploration_runtime: dict[str, Any],
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
    review_feedback: str,
    use_llm: bool | None = None,
    discovery_mode: str | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    external_task = previous_exploration_runtime.get("external_task") or {}
    task_id = str(external_task.get("task_id") or "").strip()
    if not task_id:
        raise MultiAgentExplorationError("previous exploration runtime does not include external_task.task_id")
    resolved_use_llm = bool(use_llm if use_llm is not None else external_task.get("metadata", {}).get("use_llm", False))
    resolved_mode = str(discovery_mode or external_task.get("discovery_mode") or "emergent")
    payload = {
        "backend_root": str(_EXTERNAL_BACKEND_ROOT.resolve()),
        "rerun_task_id": task_id,
        "use_llm": resolved_use_llm,
        "discovery_mode": resolved_mode,
        "timeout_seconds": int(timeout_seconds),
        "metadata": {
            "review_feedback": review_feedback,
            "rerun_source": "review_rejected",
        },
    }
    completed = subprocess.run(
        [str(_EXTERNAL_BACKEND_PYTHON), str(_RUNNER_SCRIPT)],
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        capture_output=True,
        cwd=str(_EXTERNAL_BACKEND_ROOT),
        timeout=max(5, int(timeout_seconds) + 10),
        check=False,
    )
    if completed.returncode != 0:
        raise MultiAgentExplorationError(
            f"multi-agent exploration rerun failed ({completed.returncode}): {completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        runner_payload = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError as exc:
        raise MultiAgentExplorationError(
            f"invalid exploration rerun output: {completed.stdout[:400]}"
        ) from exc
    if not runner_payload.get("success", False):
        raise MultiAgentExplorationError(f"exploration rerun returned failure: {runner_payload}")
    return _map_runner_payload(
        runner_payload=runner_payload,
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
