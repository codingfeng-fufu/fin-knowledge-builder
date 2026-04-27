from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..datasets import DEFAULT_DATASET_DIR, DEFAULT_RERUN_TRACE_DIR
from ..registry.registry_store import DEFAULT_DB_PATH


class ApiRequestError(ValueError):
    """Raised when the API request payload is malformed."""


def coerce_request(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ApiRequestError("payload must be an object")

    action = payload.get("action")
    if not isinstance(action, str) or not action:
        raise ApiRequestError("payload.action must be a non-empty string")

    request_id = payload.get("request_id")
    if request_id is not None and not isinstance(request_id, str):
        raise ApiRequestError("payload.request_id must be a string when provided")

    dataset_dir = str(payload.get("dataset_dir", DEFAULT_DATASET_DIR))
    trace_dir = str(payload.get("trace_dir", DEFAULT_RERUN_TRACE_DIR))
    db_path = str(payload.get("db_path", DEFAULT_DB_PATH))
    work_dir = str(payload.get("work_dir", "phase1_runtime/prototype_runs"))

    flow_id = payload.get("flow_id")
    if flow_id is not None and not isinstance(flow_id, str):
        raise ApiRequestError("payload.flow_id must be a string when provided")

    scenario_id = payload.get("scenario_id")
    if scenario_id is not None and not isinstance(scenario_id, str):
        raise ApiRequestError("payload.scenario_id must be a string when provided")

    question_text = payload.get("question_text")
    if question_text is not None and not isinstance(question_text, str):
        raise ApiRequestError("payload.question_text must be a string when provided")

    materials = payload.get("materials")
    if materials is not None:
        if not isinstance(materials, list):
            raise ApiRequestError("payload.materials must be a list when provided")
        for item in materials:
            if not isinstance(item, dict):
                raise ApiRequestError("payload.materials[] must be objects")
            if "name" in item and not isinstance(item["name"], str):
                raise ApiRequestError("payload.materials[].name must be a string when provided")
            if "content" in item and not isinstance(item["content"], str):
                raise ApiRequestError("payload.materials[].content must be a string when provided")
            if "content_base64" in item and not isinstance(item["content_base64"], str):
                raise ApiRequestError("payload.materials[].content_base64 must be a string when provided")
            if "media_type" in item and not isinstance(item["media_type"], str):
                raise ApiRequestError("payload.materials[].media_type must be a string when provided")
            if "size" in item and not isinstance(item["size"], int):
                raise ApiRequestError("payload.materials[].size must be an integer when provided")

    dataset_id = payload.get("dataset_id")
    if dataset_id is not None and not isinstance(dataset_id, str):
        raise ApiRequestError("payload.dataset_id must be a string when provided")

    run_id = payload.get("run_id")
    if run_id is not None and not isinstance(run_id, str):
        raise ApiRequestError("payload.run_id must be a string when provided")

    case_id = payload.get("case_id")
    if case_id is not None and not isinstance(case_id, str):
        raise ApiRequestError("payload.case_id must be a string when provided")

    case_ref = payload.get("case_ref")
    if case_ref is not None and not isinstance(case_ref, str):
        raise ApiRequestError("payload.case_ref must be a string when provided")

    draft_id = payload.get("draft_id")
    if draft_id is not None and not isinstance(draft_id, str):
        raise ApiRequestError("payload.draft_id must be a string when provided")

    review_task_id = payload.get("review_task_id")
    if review_task_id is not None and not isinstance(review_task_id, str):
        raise ApiRequestError("payload.review_task_id must be a string when provided")

    workspace_run_id = payload.get("workspace_run_id")
    if workspace_run_id is not None and not isinstance(workspace_run_id, str):
        raise ApiRequestError("payload.workspace_run_id must be a string when provided")

    rule_version_id = payload.get("rule_version_id")
    if rule_version_id is not None and not isinstance(rule_version_id, str):
        raise ApiRequestError("payload.rule_version_id must be a string when provided")

    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ApiRequestError("payload.metadata must be an object when provided")

    payload_data = payload.get("payload")
    if payload_data is not None and not isinstance(payload_data, dict):
        raise ApiRequestError("payload.payload must be an object when provided")

    trace_id = payload.get("trace_id")
    if trace_id is not None and not isinstance(trace_id, str):
        raise ApiRequestError("payload.trace_id must be a string when provided")

    feedback_id = payload.get("feedback_id")
    if feedback_id is not None and not isinstance(feedback_id, str):
        raise ApiRequestError("payload.feedback_id must be a string when provided")

    feedback_type = payload.get("feedback_type")
    if feedback_type is not None and not isinstance(feedback_type, str):
        raise ApiRequestError("payload.feedback_type must be a string when provided")

    route_decision = payload.get("route_decision")
    if route_decision is not None and not isinstance(route_decision, str):
        raise ApiRequestError("payload.route_decision must be a string when provided")

    rule_ids = payload.get("rule_ids")
    if rule_ids is not None:
        if not isinstance(rule_ids, list) or any(not isinstance(item, str) for item in rule_ids):
            raise ApiRequestError("payload.rule_ids must be a list of strings when provided")

    source = payload.get("source", "manual")
    if not isinstance(source, str):
        raise ApiRequestError("payload.source must be a string when provided")

    assignee = payload.get("assignee")
    if assignee is not None and not isinstance(assignee, str):
        raise ApiRequestError("payload.assignee must be a string when provided")

    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise ApiRequestError("payload.note must be a string when provided")

    reason = payload.get("reason")
    if reason is not None and not isinstance(reason, str):
        raise ApiRequestError("payload.reason must be a string when provided")

    return {
        "action": action,
        "request_id": request_id,
        "dataset_dir": dataset_dir,
        "trace_dir": trace_dir,
        "db_path": db_path,
        "work_dir": work_dir,
        "flow_id": flow_id,
        "scenario_id": scenario_id,
        "question_text": question_text,
        "materials": [] if materials is None else materials,
        "dataset_id": dataset_id,
        "run_id": run_id,
        "case_id": case_id,
        "case_ref": case_ref,
        "draft_id": draft_id,
        "review_task_id": review_task_id,
        "workspace_run_id": workspace_run_id,
        "rule_version_id": rule_version_id,
        "trace_id": trace_id,
        "feedback_id": feedback_id,
        "feedback_type": feedback_type,
        "route_decision": route_decision,
        "rule_ids": [] if rule_ids is None else rule_ids,
        "metadata": {} if metadata is None else metadata,
        "payload_data": {} if payload_data is None else payload_data,
        "source": source,
        "assignee": assignee,
        "note": note,
        "reason": reason,
    }


def load_cli_payload(args: Any) -> dict[str, Any]:
    if args.payload and args.payload_file:
        raise ApiRequestError("use either --payload or --payload-file, not both")
    if args.payload_file:
        return json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
    if args.payload:
        return json.loads(args.payload)

    import sys

    raw = sys.stdin.read().strip()
    if not raw:
        return {"action": "workflow.full"}
    return json.loads(raw)
