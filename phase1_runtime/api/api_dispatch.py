from __future__ import annotations

from typing import Any

from ..agents import run_super_agent
from ..datasets import (
    import_dataset_dir,
    replay_imported_dataset,
    rerun_imported_dataset,
    run_full_workflow,
    summarize_imported_dataset,
)
from ..factory import (
    approve_review,
    create_review_for_draft,
    generate_candidate_rule_draft,
    get_case,
    get_feedback_service,
    get_review,
    get_rule_draft,
    get_rule_version_service,
    get_workspace_run_service,
    ingest_case_from_dataset,
    list_case_rule_links_service,
    list_cases,
    list_feedback_service,
    list_reviews,
    list_rollbacks_service,
    list_rule_drafts,
    list_rule_versions_service,
    list_workspace_runs_service,
    promote_feedback_to_draft,
    record_feedback,
    reject_review,
    retrieval_asset_view_service,
    rule_graph_view_service,
    rollback_rule_version_service,
)
from ..product import (
    get_workspace_contract,
    list_product_scenarios,
    solve_product_request,
    solve_workspace_exploration_poll,
    solve_workspace_request,
)
from ..prototype import (
    get_workspace_demo_case,
    list_prototype_flows,
    list_workspace_demo_cases,
    run_prototype_flow,
)
from ..registry import (
    get_registered_dataset,
    get_workflow_run,
    list_registered_datasets,
    list_workflow_runs,
    register_dataset,
    run_registered_workflow_sync,
    submit_registered_workflow,
)
from ..retrieval import get_embedding_backend_status
from ..contracts import validate_dataset_dir
from .api_request import ApiRequestError


SUPPORTED_ACTIONS = [
    "dataset.validate",
    "dataset.import",
    "dataset.summary",
    "dataset.replay",
    "dataset.rerun",
    "workflow.full",
    "prototype.flow.list",
    "prototype.flow.run",
    "product.scenario.list",
    "product.solve.preview",
    "product.workspace.contract",
    "product.workspace.solve",
    "product.workspace.exploration_poll",
    "super_agent.run",
    "retrieval.embedding_backend.status",
    "demo.workspace_case.list",
    "demo.workspace_case.get",
    "registry.dataset.register",
    "registry.dataset.list",
    "registry.dataset.get",
    "registry.workflow.run",
    "registry.workflow.run_sync",
    "registry.workflow.list",
    "registry.workflow.get",
    "factory.case.ingest",
    "factory.case.list",
    "factory.case.get",
    "factory.draft.generate",
    "factory.draft.list",
    "factory.draft.get",
    "factory.review.create",
    "factory.review.list",
    "factory.review.get",
    "factory.review.approve",
    "factory.review.reject",
    "factory.rule_version.list",
    "factory.rule_version.get",
    "factory.rule_version.rollback",
    "factory.case_rule_link.list",
    "factory.rollback.list",
    "factory.workspace_run.list",
    "factory.workspace_run.get",
    "factory.feedback.promote_to_draft",
    "factory.retrieval_asset_view",
    "factory.rule_graph.view",
    "feedback.record",
    "feedback.list",
    "feedback.get",
]


class UnsupportedActionError(ValueError):
    def __init__(self, action: str) -> None:
        super().__init__(action)
        self.action = action


def dispatch_request(request: dict[str, Any], kimi_client: Any | None = None) -> dict[str, Any]:
    action = request["action"]
    request_id = request["request_id"]
    dataset_dir = request["dataset_dir"]
    trace_dir = request["trace_dir"]
    db_path = request["db_path"]
    work_dir = request["work_dir"]
    flow_id = request["flow_id"]
    scenario_id = request["scenario_id"]
    question_text = request["question_text"]
    materials = request["materials"]
    dataset_id = request["dataset_id"]
    run_id = request["run_id"]
    case_id = request["case_id"]
    case_ref = request["case_ref"]
    draft_id = request["draft_id"]
    review_task_id = request["review_task_id"]
    workspace_run_id = request["workspace_run_id"]
    rule_version_id = request["rule_version_id"]
    trace_id = request["trace_id"]
    feedback_id = request["feedback_id"]
    feedback_type = request["feedback_type"]
    route_decision = request["route_decision"]
    rule_ids = request["rule_ids"]
    metadata = request["metadata"]
    payload_data = request["payload_data"]
    source = request["source"]
    assignee = request["assignee"]
    note = request["note"]
    reason = request["reason"]

    if action == "dataset.validate":
        return validate_dataset_dir(dataset_dir)
    if action == "dataset.import":
        return import_dataset_dir(dataset_dir).to_summary()
    if action == "dataset.summary":
        return summarize_imported_dataset(import_dataset_dir(dataset_dir))
    if action == "dataset.replay":
        return replay_imported_dataset(import_dataset_dir(dataset_dir))
    if action == "dataset.rerun":
        return rerun_imported_dataset(import_dataset_dir(dataset_dir), trace_dir=trace_dir, db_path=db_path)
    if action == "workflow.full":
        return run_full_workflow(dataset_dir=dataset_dir, trace_dir=trace_dir, db_path=db_path)
    if action == "prototype.flow.list":
        return list_prototype_flows()
    if action == "prototype.flow.run":
        if not flow_id:
            raise ApiRequestError("payload.flow_id is required for prototype.flow.run")
        return run_prototype_flow(flow_id=flow_id, work_dir=work_dir, db_path=db_path)
    if action == "product.scenario.list":
        return list_product_scenarios()
    if action == "product.solve.preview":
        return solve_product_request(scenario_id=scenario_id or "fund_nav_warning", question_text=question_text, work_dir=work_dir, db_path=db_path)
    if action == "product.workspace.contract":
        return get_workspace_contract()
    if action == "product.workspace.solve":
        use_live_kimi = bool(metadata.get("use_live_kimi", True)) if isinstance(metadata, dict) else True
        run_live_super_agent = bool(metadata.get("run_live_super_agent")) if isinstance(metadata, dict) else False
        super_agent_backend = str(metadata.get("super_agent_backend") or "builtin") if isinstance(metadata, dict) else "builtin"
        coding_agent_check_command = metadata.get("coding_agent_check_command") if isinstance(metadata, dict) else None
        coding_agent_review_with_agent = bool(metadata.get("coding_agent_review_with_agent")) if isinstance(metadata, dict) else False
        coding_agent_provider = str(metadata.get("coding_agent_provider") or "auto") if isinstance(metadata, dict) else "auto"
        exploration_backend = str(metadata.get("exploration_backend") or "multi_agent_exploration") if isinstance(metadata, dict) else "multi_agent_exploration"
        exploration_use_llm = bool(metadata.get("exploration_use_llm")) if isinstance(metadata, dict) else True
        exploration_mode = str(metadata.get("exploration_mode") or "emergent") if isinstance(metadata, dict) else "emergent"
        return solve_workspace_request(
            question_text=question_text or "",
            materials=materials,
            scenario_id=scenario_id,
            work_dir=work_dir,
            db_path=db_path,
            kimi_client=kimi_client,
            use_live_kimi=use_live_kimi or kimi_client is not None,
            run_live_super_agent=run_live_super_agent,
            super_agent_backend=super_agent_backend,
            coding_agent_check_command=str(coding_agent_check_command) if isinstance(coding_agent_check_command, str) else None,
            coding_agent_review_with_agent=coding_agent_review_with_agent,
            coding_agent_provider=coding_agent_provider,
            exploration_backend=exploration_backend,
            exploration_use_llm=exploration_use_llm,
            exploration_mode=exploration_mode,
        )
    if action == "product.workspace.exploration_poll":
        task_id = str((payload_data or {}).get("exploration_task_id") or "").strip()
        if not task_id:
            raise ApiRequestError("payload.payload.exploration_task_id is required for product.workspace.exploration_poll")
        return solve_workspace_exploration_poll(task_id=task_id, work_dir=work_dir)
    if action == "super_agent.run":
        query = payload_data.get("query") or question_text or ""
        skill_root = payload_data.get("skill_root")
        workspace_root = payload_data.get("workspace_root") or work_dir
        task_context = payload_data.get("task_context")
        context_packet = payload_data.get("context_packet")
        max_turns = int(payload_data.get("max_turns") or 8)
        backend = str(payload_data.get("backend") or "builtin")
        coding_agent_check_command = payload_data.get("coding_agent_check_command")
        coding_agent_review_with_agent = bool(payload_data.get("coding_agent_review_with_agent", False))
        coding_agent_provider = str(payload_data.get("coding_agent_provider") or "auto")
        if not isinstance(skill_root, str) or not skill_root:
            raise ApiRequestError("payload.payload.skill_root is required for super_agent.run")
        if task_context is not None and not isinstance(task_context, dict):
            raise ApiRequestError("payload.payload.task_context must be an object when provided")
        if context_packet is not None and not isinstance(context_packet, dict):
            raise ApiRequestError("payload.payload.context_packet must be an object when provided")
        return run_super_agent(
            query=str(query),
            skill_root=skill_root,
            workspace_root=str(workspace_root),
            task_context=task_context,
            context_packet=context_packet,
            max_turns=max_turns,
            kimi_client=kimi_client,
            backend=backend,
            coding_agent_check_command=str(coding_agent_check_command) if isinstance(coding_agent_check_command, str) else None,
            coding_agent_review_with_agent=coding_agent_review_with_agent,
            coding_agent_provider=coding_agent_provider,
        )
    if action == "retrieval.embedding_backend.status":
        return get_embedding_backend_status()
    if action == "demo.workspace_case.list":
        return list_workspace_demo_cases()
    if action == "demo.workspace_case.get":
        if not case_ref:
            raise ApiRequestError("payload.case_ref is required for demo.workspace_case.get")
        return get_workspace_demo_case(case_ref=case_ref)
    if action == "registry.dataset.register":
        return register_dataset(dataset_dir=dataset_dir, source=source, metadata=metadata, db_path=db_path)
    if action == "registry.dataset.list":
        return list_registered_datasets(db_path=db_path)
    if action == "registry.dataset.get":
        if not dataset_id:
            raise ApiRequestError("payload.dataset_id is required for registry.dataset.get")
        return get_registered_dataset(dataset_id=dataset_id, db_path=db_path)
    if action == "registry.workflow.run":
        if not dataset_id:
            raise ApiRequestError("payload.dataset_id is required for registry.workflow.run")
        return submit_registered_workflow(dataset_id=dataset_id, request_id=request_id, trace_dir=trace_dir, db_path=db_path)
    if action == "registry.workflow.run_sync":
        if not dataset_id:
            raise ApiRequestError("payload.dataset_id is required for registry.workflow.run_sync")
        return run_registered_workflow_sync(dataset_id=dataset_id, request_id=request_id, trace_dir=trace_dir, db_path=db_path)
    if action == "registry.workflow.list":
        return list_workflow_runs(db_path=db_path)
    if action == "registry.workflow.get":
        if not run_id:
            raise ApiRequestError("payload.run_id is required for registry.workflow.get")
        return get_workflow_run(run_id=run_id, db_path=db_path)
    if action == "factory.case.ingest":
        return ingest_case_from_dataset(dataset_dir=dataset_dir, source=source, db_path=db_path)
    if action == "factory.case.list":
        return list_cases(db_path=db_path)
    if action == "factory.case.get":
        if not case_id:
            raise ApiRequestError("payload.case_id is required for factory.case.get")
        return get_case(case_id=case_id, db_path=db_path)
    if action == "factory.draft.generate":
        if not case_id:
            raise ApiRequestError("payload.case_id is required for factory.draft.generate")
        return generate_candidate_rule_draft(case_id=case_id, db_path=db_path)
    if action == "factory.draft.list":
        return list_rule_drafts(db_path=db_path)
    if action == "factory.draft.get":
        if not draft_id:
            raise ApiRequestError("payload.draft_id is required for factory.draft.get")
        return get_rule_draft(draft_id=draft_id, db_path=db_path)
    if action == "factory.review.create":
        if not draft_id:
            raise ApiRequestError("payload.draft_id is required for factory.review.create")
        if assignee:
            return create_review_for_draft(draft_id=draft_id, assignee=assignee, db_path=db_path)
        return create_review_for_draft(draft_id=draft_id, db_path=db_path)
    if action == "factory.review.list":
        return list_reviews(db_path=db_path)
    if action == "factory.review.get":
        if not review_task_id:
            raise ApiRequestError("payload.review_task_id is required for factory.review.get")
        return get_review(review_task_id=review_task_id, db_path=db_path)
    if action == "factory.review.approve":
        if not review_task_id:
            raise ApiRequestError("payload.review_task_id is required for factory.review.approve")
        if note is not None:
            return approve_review(review_task_id=review_task_id, note=note, db_path=db_path)
        return approve_review(review_task_id=review_task_id, db_path=db_path)
    if action == "factory.review.reject":
        if not review_task_id:
            raise ApiRequestError("payload.review_task_id is required for factory.review.reject")
        if note is not None:
            return reject_review(review_task_id=review_task_id, note=note, db_path=db_path)
        return reject_review(review_task_id=review_task_id, db_path=db_path)
    if action == "factory.rule_version.list":
        return list_rule_versions_service(db_path=db_path)
    if action == "factory.rule_version.get":
        if not rule_version_id:
            raise ApiRequestError("payload.rule_version_id is required for factory.rule_version.get")
        return get_rule_version_service(rule_version_id=rule_version_id, db_path=db_path)
    if action == "factory.rule_version.rollback":
        if not rule_version_id:
            raise ApiRequestError("payload.rule_version_id is required for factory.rule_version.rollback")
        if not reason:
            raise ApiRequestError("payload.reason is required for factory.rule_version.rollback")
        return rollback_rule_version_service(rule_version_id=rule_version_id, reason=reason, db_path=db_path)
    if action == "factory.case_rule_link.list":
        return list_case_rule_links_service(db_path=db_path)
    if action == "factory.rollback.list":
        return list_rollbacks_service(db_path=db_path)
    if action == "factory.workspace_run.list":
        return list_workspace_runs_service(db_path=db_path)
    if action == "factory.workspace_run.get":
        if not workspace_run_id:
            raise ApiRequestError("payload.workspace_run_id is required for factory.workspace_run.get")
        return get_workspace_run_service(workspace_run_id=workspace_run_id, db_path=db_path)
    if action == "factory.feedback.promote_to_draft":
        if not feedback_id:
            raise ApiRequestError("payload.feedback_id is required for factory.feedback.promote_to_draft")
        return promote_feedback_to_draft(feedback_id=feedback_id, db_path=db_path)
    if action == "factory.retrieval_asset_view":
        return retrieval_asset_view_service(db_path=db_path)
    if action == "factory.rule_graph.view":
        return rule_graph_view_service(db_path=db_path)
    if action == "feedback.record":
        if not trace_id:
            raise ApiRequestError("payload.trace_id is required for feedback.record")
        if not route_decision:
            raise ApiRequestError("payload.route_decision is required for feedback.record")
        if not feedback_type:
            raise ApiRequestError("payload.feedback_type is required for feedback.record")
        return record_feedback(
            trace_id=trace_id,
            route_decision=route_decision,
            feedback_type=feedback_type,
            rule_ids=rule_ids,
            payload=payload_data,
            case_id=case_id,
            db_path=db_path,
        )
    if action == "feedback.list":
        return list_feedback_service(db_path=db_path)
    if action == "feedback.get":
        if not feedback_id:
            raise ApiRequestError("payload.feedback_id is required for feedback.get")
        return get_feedback_service(feedback_id=feedback_id, db_path=db_path)

    raise UnsupportedActionError(action)
