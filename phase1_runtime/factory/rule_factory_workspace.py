from __future__ import annotations

from pathlib import Path
from typing import Any

from ..registry.registry_store import DEFAULT_DB_PATH
from .rule_factory_feedback import promote_feedback_to_draft, record_feedback
from .rule_factory_store import (
    ensure_rule_factory_db,
    get_workspace_run_record,
    insert_workspace_run_record,
    list_workspace_run_records,
    upsert_case_record,
)


def workspace_feedback_plan(
    *,
    route_decision: str,
    runtime_status: str,
    final_decision: str,
    matched_rule_id: str | None,
    source_rule_ids: list[str],
    fallback_rule_ids: list[str],
) -> dict[str, Any] | None:
    if route_decision == 'needs_more_context':
        # User needs to provide more material — don't promote to draft, just record
        return None
    if route_decision == 'rule_composable' and source_rule_ids:
        return {
            'feedback_type': 'stable_composition',
            'rule_ids': list(source_rule_ids),
            'should_promote': True,
        }
    if route_decision == 'exploration':
        return {
            'feedback_type': 'missed_rule',
            'rule_ids': list(source_rule_ids) or list(fallback_rule_ids[:1]),
            'should_promote': True,
        }
    if runtime_status != 'completed' or final_decision == 'needs_review':
        chosen_rule_ids = []
        if matched_rule_id:
            chosen_rule_ids = [matched_rule_id]
        elif fallback_rule_ids:
            chosen_rule_ids = [fallback_rule_ids[0]]
        return {
            'feedback_type': 'bad_final_answer',
            'rule_ids': chosen_rule_ids,
            'should_promote': True,
        }
    return None


def record_workspace_run(
    *,
    trace_id: str,
    scenario_id: str,
    question_text: str,
    route_decision: str,
    runtime_status: str,
    final_decision: str,
    final_answer: str,
    parser_status: str,
    parser_bridge_status: str,
    question_packet_preview: dict[str, Any],
    document_packet_preview: dict[str, Any],
    fact_sheet: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
    task_context: dict[str, Any] | None = None,
    rule_bindings: list[dict[str, Any]] | None = None,
    runtime_skill_spec_preview: dict[str, Any] | None = None,
    feedback_payload: dict[str, Any],
    uploaded_materials: list[dict[str, Any]],
    unsupported_files: list[dict[str, Any]],
    embedding_backend: dict[str, Any] | None = None,
    retrieval_diagnostics: dict[str, Any] | None = None,
    matched_rule_id: str | None = None,
    source_rule_ids: list[str] | None = None,
    fallback_rule_ids: list[str] | None = None,
    trace_path: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    source_rule_ids = [] if source_rule_ids is None else list(source_rule_ids)
    fallback_rule_ids = [] if fallback_rule_ids is None else list(fallback_rule_ids)
    case_id = f'workspace_case_{trace_id}'
    workspace_run_id = f'workspace_run_{trace_id}'
    case_payload = {
        'entry': 'workspace',
        'trace_id': trace_id,
        'trace_path': trace_path,
        'scenario_id': scenario_id,
        'route_decision': route_decision,
        'runtime_status': runtime_status,
        'final_decision': final_decision,
        'final_answer': final_answer,
        'parser_status': parser_status,
        'parser_bridge_status': parser_bridge_status,
        'question_packet_preview': question_packet_preview,
        'document_packet_preview': document_packet_preview,
        'fact_sheet': fact_sheet,
        'documents': documents,
        'evidence_refs': evidence_refs,
        'task_context': {} if task_context is None else dict(task_context),
        'rule_bindings': [] if rule_bindings is None else list(rule_bindings),
        'runtime_skill_spec_preview': {} if runtime_skill_spec_preview is None else dict(runtime_skill_spec_preview),
        'uploaded_materials': uploaded_materials,
        'unsupported_files': unsupported_files,
        'embedding_backend': {} if embedding_backend is None else dict(embedding_backend),
        'retrieval_diagnostics': {} if retrieval_diagnostics is None else dict(retrieval_diagnostics),
    }
    case = upsert_case_record(
        case_id=case_id,
        dataset_id=f'workspace_{scenario_id}',
        scenario_name=scenario_id,
        dataset_dir=f'workspace://{scenario_id}/{trace_id}',
        title=f'workspace_run_{scenario_id}',
        question_text=question_text,
        review_status='unreviewed',
        source='workspace_run',
        payload=case_payload,
        db_path=db_path,
    )

    feedback_plan = workspace_feedback_plan(
        route_decision=route_decision,
        runtime_status=runtime_status,
        final_decision=final_decision,
        matched_rule_id=matched_rule_id,
        source_rule_ids=source_rule_ids,
        fallback_rule_ids=fallback_rule_ids,
    )

    feedback = None
    promotion = None
    review = None
    auto_status = 'recorded_only'
    auto_error = None
    if feedback_plan is not None:
        feedback = record_feedback(
            trace_id=trace_id,
            case_id=case_id,
            route_decision=route_decision,
            feedback_type=feedback_plan['feedback_type'],
            rule_ids=feedback_plan['rule_ids'],
            payload=feedback_payload,
            db_path=db_path,
        )
        auto_status = 'feedback_recorded'
        if feedback_plan['should_promote']:
            try:
                promotion = promote_feedback_to_draft(feedback['feedback_id'], db_path=db_path)
                from .rule_factory_review_flow import create_review_for_draft
                review = create_review_for_draft(promotion['draft']['draft_id'], db_path=db_path)
                auto_status = 'draft_promoted'
            except Exception as exc:
                auto_status = 'feedback_recorded_draft_failed'
                auto_error = str(exc)

    workspace_run = insert_workspace_run_record(
        workspace_run_id=workspace_run_id,
        trace_id=trace_id,
        case_id=case_id,
        scenario_id=scenario_id,
        question_text=question_text,
        route_decision=route_decision,
        final_decision=final_decision,
        status=runtime_status,
        payload={
            'parser_status': parser_status,
            'parser_bridge_status': parser_bridge_status,
            'final_answer': final_answer,
            'trace_path': trace_path,
            'feedback_payload': feedback_payload,
            'task_context': {} if task_context is None else dict(task_context),
            'rule_bindings': [] if rule_bindings is None else list(rule_bindings),
            'runtime_skill_spec_preview': {} if runtime_skill_spec_preview is None else dict(runtime_skill_spec_preview),
            'matched_rule_id': matched_rule_id,
            'source_rule_ids': source_rule_ids,
            'fallback_rule_ids': fallback_rule_ids,
            'embedding_backend': {} if embedding_backend is None else dict(embedding_backend),
            'retrieval_diagnostics': {} if retrieval_diagnostics is None else dict(retrieval_diagnostics),
            'auto_status': auto_status,
            'auto_error': auto_error,
            'feedback_id': None if feedback is None else feedback['feedback_id'],
            'draft_id': None if promotion is None else promotion['draft']['draft_id'],
        },
        db_path=db_path,
    )
    return {
        'workspace_run': workspace_run,
        'case': case,
        'feedback': feedback,
        'promotion': promotion,
        'review': review,
        'auto_status': auto_status,
        'auto_error': auto_error,
    }


def list_workspace_runs_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_workspace_run_records(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'workspace_run_count': len(items),
        'workspace_runs': items,
    }


def get_workspace_run_service(workspace_run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_workspace_run_record(workspace_run_id, db_path=db_path)
