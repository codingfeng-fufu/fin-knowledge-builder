from __future__ import annotations

from pathlib import Path
import tempfile
from typing import Any
from uuid import uuid4

from ..agents import run_super_agent
from ..analysis import rerun_multi_agent_exploration
from ..retrieval.rule_graph_store import rebuild_active_rule_graph_artifacts
from ..registry.registry_store import DEFAULT_DB_PATH
from ..runtime_core import Phase1Runtime, bind_rule
from ..runtime_core.task_context import ContextFactEntry, TaskContext, build_task_context
from ..schema import Rule
from ..skills import compile_rule_to_reusable_skill, materialize_skill_artifact, validate_skill_artifact
from .rule_factory_errors import RuleFactoryError
from .rule_factory_feedback import get_feedback_service, promote_feedback_to_draft, record_feedback
from .rule_factory_publish_utils import asset_type_from_rule_kind, build_published_rule_payload
from .rule_factory_store import (
    count_rule_versions,
    ensure_rule_factory_db,
    get_candidate_rule_draft,
    get_case_record,
    get_review_task,
    insert_case_rule_link,
    insert_review_task,
    insert_rule_version,
    list_review_tasks,
    list_rule_versions,
    update_candidate_rule_draft_status,
    update_review_task,
)
from .rule_factory_validation import (
    source_validation_rules,
    validate_review_for_publish,
    workspace_case_validation_bundle,
)


def _task_context_from_source_payload(source_payload: dict[str, Any]) -> TaskContext | None:
    raw_task_context = source_payload.get('task_context')
    if isinstance(raw_task_context, dict) and raw_task_context.get('fact_entries'):
        fact_entries = [
            ContextFactEntry(
                fact_id=str(item.get('fact_id')),
                fact_type=str(item.get('fact_type', 'unknown')),
                value=item.get('value'),
                status=str(item.get('status', 'grounded')),
                source=str(item.get('source', 'workspace')),
                evidence_refs=list(item.get('evidence_refs', [])),
            )
            for item in raw_task_context.get('fact_entries', [])
            if isinstance(item, dict) and item.get('fact_id')
        ]
        return TaskContext(
            context_id=str(raw_task_context.get('context_id') or f"context_preview_{uuid4().hex[:12]}"),
            question_text=str(raw_task_context.get('question_text') or source_payload.get('question_text') or ''),
            scenario_hint=str(raw_task_context.get('scenario_hint') or source_payload.get('scenario_id') or ''),
            parser_status=str(raw_task_context.get('parser_status') or source_payload.get('parser_status') or 'parsed_complete'),
            context_status=str(raw_task_context.get('context_status') or 'grounded_enough'),
            completeness_score=float(raw_task_context.get('completeness_score', 0.0) or 0.0),
            document_refs=list(raw_task_context.get('document_refs', [])),
            fact_entries=fact_entries,
            evidence_packets=list(raw_task_context.get('evidence_packets', [])),
            unresolved_slots=list(raw_task_context.get('unresolved_slots', [])),
            derived_values=list(raw_task_context.get('derived_values', [])),
        )

    question_text = str(source_payload.get('question_text') or '')
    scenario_id = str(source_payload.get('scenario_id') or '')
    if not question_text or not scenario_id:
        return None
    document_packet_preview = source_payload.get('document_packet_preview', {}) if isinstance(source_payload.get('document_packet_preview', {}), dict) else {}
    documents = list(document_packet_preview.get('documents', [])) if isinstance(document_packet_preview.get('documents', []), list) else []
    fact_sheet = list(source_payload.get('fact_sheet', [])) if isinstance(source_payload.get('fact_sheet', []), list) else []
    evidence_refs = list(source_payload.get('evidence_refs', [])) if isinstance(source_payload.get('evidence_refs', []), list) else []
    missing_fact_keys = list(source_payload.get('missing_fact_keys', [])) if isinstance(source_payload.get('missing_fact_keys', []), list) else []
    return build_task_context(
        question_text=question_text,
        scenario_hint=scenario_id,
        parser_status=str(source_payload.get('parser_status') or 'parsed_complete'),
        documents=documents,
        fact_sheet=fact_sheet,
        evidence_packets=evidence_refs,
        unresolved_slots=missing_fact_keys,
    )


def _open_review_for_draft(draft_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    for review in list_review_tasks(db_path=db_path):
        if review.get('draft_id') == draft_id and review.get('status') == 'open':
            return review
    return None


def _preview_draft_execution(
    draft: dict[str, Any],
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    case = get_case_record(draft['case_id'], db_path=db_path)
    candidate_rule = Rule.from_dict(
        build_published_rule_payload(
            draft=draft,
            review=None,
            version_label='preview',
            status='candidate',
        )
    )
    if str(case['dataset_dir']).startswith('workspace://'):
        source_bundle = workspace_case_validation_bundle(case)
        runtime_rules = {rule.rule_id: rule for rule in source_validation_rules(draft, db_path=db_path)}
        runtime_rules[candidate_rule.rule_id] = candidate_rule
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, min_signal_hits=1, retrieval_top_k=5)
            rerun = runtime.run(
                question=source_bundle['question'],
                rules=list(runtime_rules.values()),
                facts=source_bundle['facts'],
                evidence_refs=source_bundle['evidence_refs'],
            )
            preview_workspace_root = Path(tmpdir)
    else:
        imported = get_case_record(draft['case_id'], db_path=db_path)
        dataset_dir = imported['dataset_dir']
        from ..datasets import import_dataset_dir

        dataset = import_dataset_dir(dataset_dir)
        runtime_rules = {rule.rule_id: rule for rule in dataset.rule_pool}
        runtime_rules[candidate_rule.rule_id] = candidate_rule
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Phase1Runtime(trace_dir=tmpdir, min_signal_hits=1, retrieval_top_k=5)
            rerun = runtime.run(
                question=dataset.question,
                rules=list(runtime_rules.values()),
                facts=dataset.document_bundle.facts,
                evidence_refs=dataset.document_bundle.evidence_refs,
            )
            preview_workspace_root = Path(tmpdir)
    rerun_result = rerun.final_result or {}
    source_payload = draft.get('payload', {}).get('feedback_context', {}).get('source_payload', {})
    task_context = _task_context_from_source_payload(source_payload if isinstance(source_payload, dict) else {})
    method_draft_preview = None
    agent_preview: dict[str, Any] | None = None
    if task_context is not None:
        binding = bind_rule(candidate_rule, task_context)
        artifact = compile_rule_to_reusable_skill(
            candidate_rule,
            task_context,
            binding,
            include_references=True,
        )
        skill_root = materialize_skill_artifact(
            artifact,
            preview_workspace_root / "candidate_rule_previews" / rerun.trace_id,
        )
        method_draft_preview = {
            'skill_name': artifact.skill_name,
            'description': artifact.description,
            'binding_status': binding.binding_status,
            'skill_root': str(skill_root),
            'validation': validate_skill_artifact(skill_root),
        }
        context_packet = source_payload.get('context_packet', {}) if isinstance(source_payload.get('context_packet', {}), dict) else {}
        try:
            agent_result = run_super_agent(
                query=str(source_payload.get('question_text') or candidate_rule.name),
                skill_root=skill_root,
                workspace_root=preview_workspace_root,
                task_context=task_context.to_dict(),
                context_packet=context_packet,
                max_turns=6,
            )
            agent_preview = {
                'status': 'completed',
                'answer_source': 'super_agent',
                'final_text': agent_result.get('final_text'),
                'turns': agent_result.get('turns'),
                'tool_call_count': agent_result.get('tool_call_count'),
            }
        except Exception as exc:
            agent_preview = {
                'status': 'skipped',
                'reason': str(exc),
            }

    return {
        'runtime_preview': {
            'status': rerun.status,
            'route_decision': rerun.route_decision,
            'matched_rule_id': rerun.matched_rule_id,
            'final_decision': rerun_result.get('decision'),
            'final_answer': rerun_result.get('answer_text') or rerun_result.get('explanation'),
            'trace_id': rerun.trace_id,
            'trace_path': str(rerun.trace_path),
        },
        'method_draft_preview': method_draft_preview,
        'agent_preview': agent_preview,
    }


def _review_checklist() -> list[dict[str, Any]]:
    return [
        {'item_id': 'check_reuse', 'label': 'Rule is reusable', 'status': 'pending'},
        {'item_id': 'check_scope', 'label': 'Scope is clear', 'status': 'pending'},
        {'item_id': 'check_steps', 'label': 'Steps are complete', 'status': 'pending'},
        {'item_id': 'check_provenance', 'label': 'Provenance is complete', 'status': 'pending'},
    ]


def _build_review_payload(draft: dict[str, Any], *, db_path: str | Path) -> dict[str, Any]:
    return {
        'embedding_backend': draft['payload'].get('embedding_backend', {}),
        'runtime_skill_spec_preview': draft['payload'].get('runtime_skill_spec_preview', {}),
        'source_case_id': draft['case_id'],
        'proposed_rule_id': draft['proposed_rule_id'],
        'test_execution_preview': _preview_draft_execution(draft, db_path=db_path),
    }


def _prepare_publish_version(
    review: dict[str, Any],
    draft: dict[str, Any],
    *,
    review_task_id: str,
    note: str,
    db_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    proposed_rule_id = draft['proposed_rule_id']
    version_number = count_rule_versions(proposed_rule_id, db_path=db_path) + 1
    version_label = f'factory_v{version_number}'
    existing_versions = [
        item
        for item in list_rule_versions(db_path=db_path)
        if item['rule_id'] == proposed_rule_id and item['status'] == 'published'
    ]
    supersedes_rule_version_id = existing_versions[-1]['rule_version_id'] if existing_versions else None
    published_rule = build_published_rule_payload(
        draft=draft,
        review=review,
        version_label=version_label,
        status='published',
    )
    version_payload = {
        'rule_version_id': f'rule_version_{uuid4().hex[:12]}',
        'rule_id': proposed_rule_id,
        'version_label': version_label,
        'source_draft_id': draft['draft_id'],
        'status': 'published',
        'payload': {
            'asset_type': draft['payload'].get('asset_type', asset_type_from_rule_kind(draft['payload'].get('rule_kind', 'composite'))),
            'asset_id': draft['payload'].get('asset_id', proposed_rule_id),
            'change_type': draft['payload'].get('change_type', 'patch'),
            'source_trace_ids': list(draft['payload'].get('source_trace_ids', [])),
            'based_on_asset_ids': list(draft['payload'].get('based_on_asset_ids', [])),
            'supersedes_rule_version_id': supersedes_rule_version_id,
            'review_task_id': review_task_id,
            'approved_note': note,
            'embedding_backend': draft['payload'].get('embedding_backend', {}),
            'runtime_skill_spec_preview': draft['payload'].get('runtime_skill_spec_preview', {}),
            'draft': draft,
            'review': review,
            'rule': published_rule,
        },
    }
    return version_payload, published_rule


def _approve_review_and_publish(
    *,
    review_task_id: str,
    review: dict[str, Any],
    draft: dict[str, Any],
    note: str,
    db_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    case = get_case_record(draft['case_id'], db_path=db_path)
    version_payload, _published_rule = _prepare_publish_version(
        review,
        draft,
        review_task_id=review_task_id,
        note=note,
        db_path=db_path,
    )
    version_label = version_payload['version_label']
    source_validation = validate_review_for_publish(review, draft, version_label, case=case, db_path=db_path)

    updated_review = update_review_task(
        review_task_id=review_task_id,
        status='approved',
        result_note=note,
        checklist=[{**item, 'status': 'passed'} for item in review['checklist']],
        payload={**review.get('payload', {}), 'approved_note': note},
        db_path=db_path,
    )
    update_candidate_rule_draft_status(draft['draft_id'], 'published', db_path=db_path)
    version_payload['payload']['review'] = updated_review
    version_payload['payload']['source_validation'] = source_validation
    version_payload['payload']['rule'] = build_published_rule_payload(
        draft=draft,
        review=updated_review,
        version_label=version_label,
        status='published',
    )
    version = insert_rule_version(
        rule_version_id=version_payload['rule_version_id'],
        rule_id=version_payload['rule_id'],
        version_label=version_payload['version_label'],
        source_draft_id=version_payload['source_draft_id'],
        status=version_payload['status'],
        payload=version_payload['payload'],
        db_path=db_path,
    )
    link = insert_case_rule_link(
        link_id=f'link_{uuid4().hex[:12]}',
        case_id=draft['case_id'],
        rule_id=draft['proposed_rule_id'],
        rule_version_id=version_payload['rule_version_id'],
        relation_type='source_case',
        db_path=db_path,
    )
    rule_graph_artifacts = rebuild_active_rule_graph_artifacts(db_path=db_path)
    return updated_review, {
        'rule_version': version,
        'case_rule_link': link,
        'rule_graph_artifacts': rule_graph_artifacts,
    }


def create_review_for_draft(
    draft_id: str,
    assignee: str = 'rule_reviewer',
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    draft = get_candidate_rule_draft(draft_id, db_path=db_path)
    existing_review = _open_review_for_draft(draft_id, db_path=db_path)
    if existing_review is not None:
        return existing_review
    if draft['status'] not in {'draft', 'under_review'}:
        raise RuleFactoryError(f'draft cannot enter review from status {draft["status"]}: {draft_id}')
    if draft['status'] == 'draft':
        update_candidate_rule_draft_status(draft_id, 'under_review', db_path=db_path)
    return insert_review_task(
        review_task_id=f'review_{uuid4().hex[:12]}',
        draft_id=draft_id,
        status='open',
        assignee=assignee,
        checklist=_review_checklist(),
        result_note=None,
        payload=_build_review_payload(draft, db_path=db_path),
        db_path=db_path,
    )


def list_reviews(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_review_tasks(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'review_count': len(items),
        'reviews': items,
    }


def get_review(review_task_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_review_task(review_task_id, db_path=db_path)


def approve_review(
    review_task_id: str,
    note: str = 'approved',
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    review = get_review_task(review_task_id, db_path=db_path)
    draft = get_candidate_rule_draft(review['draft_id'], db_path=db_path)
    review, publish_payload = _approve_review_and_publish(
        review_task_id=review_task_id,
        review=review,
        draft=draft,
        note=note,
        db_path=db_path,
    )
    return {
        'review': review,
        **publish_payload,
    }


def _rerun_rejected_exploration(
    *,
    review: dict[str, Any],
    draft: dict[str, Any],
    note: str,
    db_path: str | Path,
) -> dict[str, Any] | None:
    draft_payload = draft.get('payload', {}) if isinstance(draft.get('payload', {}), dict) else {}
    feedback_context = draft_payload.get('feedback_context', {}) if isinstance(draft_payload.get('feedback_context', {}), dict) else {}
    source_payload = feedback_context.get('source_payload', {}) if isinstance(feedback_context.get('source_payload', {}), dict) else {}
    exploration_runtime = source_payload.get('exploration_runtime')
    if not isinstance(exploration_runtime, dict):
        return None
    external_task = exploration_runtime.get('external_task')
    if not isinstance(external_task, dict) or not external_task.get('task_id'):
        return None

    question_text = str(source_payload.get('question_text') or draft.get('question_text') or '')
    scenario_id = str(source_payload.get('scenario_id') or '')
    if not question_text or not scenario_id:
        return None

    original_feedback_id = feedback_context.get('feedback_id')
    original_feedback = (
        get_feedback_service(str(original_feedback_id), db_path=db_path)
        if isinstance(original_feedback_id, str) and original_feedback_id
        else None
    )
    original_rule_ids = list((original_feedback or {}).get('rule_ids', []))
    rerun_payload = rerun_multi_agent_exploration(
        previous_exploration_runtime=exploration_runtime,
        scenario_id=scenario_id,
        question_text=question_text,
        route_decision=str((original_feedback or {}).get('route_decision') or source_payload.get('route_decision') or 'exploration'),
        runtime_status=str(source_payload.get('runtime_status') or 'failed'),
        final_decision=str(source_payload.get('final_decision') or 'needs_review'),
        failure_reason=str(source_payload.get('failure_reason') or '') or None,
        parser_status=str(source_payload.get('parser_status') or 'parsed_complete'),
        missing_fact_keys=list(source_payload.get('missing_fact_keys', [])) if isinstance(source_payload.get('missing_fact_keys', []), list) else [],
        fact_sheet=list(source_payload.get('fact_sheet', [])) if isinstance(source_payload.get('fact_sheet', []), list) else [],
        documents=list(source_payload.get('document_packet_preview', {}).get('documents', [])) if isinstance(source_payload.get('document_packet_preview', {}), dict) else [],
        matched_rule_id=str(source_payload.get('matched_rule_id') or '') or None,
        source_rule_ids=original_rule_ids,
        fallback_rule_ids=original_rule_ids or [str(draft.get('source_rule_id') or draft.get('proposed_rule_id') or '')],
        review_feedback=note,
        use_llm=bool((external_task.get('metadata') or {}).get('use_llm', False)),
        discovery_mode=str(external_task.get('discovery_mode') or 'grounded'),
    )
    rerun_source_payload = dict(source_payload)
    rerun_source_payload['exploration_runtime'] = rerun_payload
    rerun_source_payload['review_feedback'] = note
    rerun_source_payload['recommended_action'] = (
        ((rerun_payload.get('candidate_rule_drafts') or [{}])[0].get('recommended_action'))
        if rerun_payload.get('candidate_rule_drafts')
        else None
    )
    rerun_feedback = record_feedback(
        trace_id=str((original_feedback or {}).get('trace_id') or feedback_context.get('source_trace_ids', [''])[0] or draft.get('case_id') or review['review_task_id']),
        case_id=draft.get('case_id'),
        route_decision=str((original_feedback or {}).get('route_decision') or 'exploration'),
        feedback_type=str(rerun_payload.get('recommended_feedback_type') or 'missed_rule'),
        rule_ids=list(rerun_payload.get('recommended_rule_ids', [])),
        payload=rerun_source_payload,
        db_path=db_path,
    )
    rerun_promotion = promote_feedback_to_draft(rerun_feedback['feedback_id'], db_path=db_path)
    rerun_draft = rerun_promotion['draft']
    rerun_review = create_review_for_draft(
        rerun_draft['draft_id'],
        assignee=review.get('assignee', ''),
        db_path=db_path,
    )
    return {
        'exploration_runtime': rerun_payload,
        'feedback': rerun_feedback,
        'promotion': rerun_promotion,
        'review': rerun_review,
    }


def _reject_review_and_maybe_rerun(
    *,
    review_task_id: str,
    review: dict[str, Any],
    draft: dict[str, Any],
    note: str,
    db_path: str | Path,
) -> dict[str, Any]:
    updated_review = update_review_task(
        review_task_id=review_task_id,
        status='rejected',
        result_note=note,
        checklist=[{**item, 'status': 'rejected'} for item in review['checklist']],
        payload={**review.get('payload', {}), 'rejected_note': note},
        db_path=db_path,
    )
    updated_draft = update_candidate_rule_draft_status(draft['draft_id'], 'rejected', db_path=db_path)
    result = {
        'review': updated_review,
        'draft': updated_draft,
    }
    try:
        rerun = _rerun_rejected_exploration(
            review=updated_review,
            draft=updated_draft,
            note=note,
            db_path=db_path,
        )
    except Exception as exc:
        result['rerun_error'] = str(exc)
        return result
    if rerun is not None:
        result['rerun'] = rerun
    return result


def reject_review(
    review_task_id: str,
    note: str = 'rejected',
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    review = get_review_task(review_task_id, db_path=db_path)
    draft = get_candidate_rule_draft(review['draft_id'], db_path=db_path)
    return _reject_review_and_maybe_rerun(
        review_task_id=review_task_id,
        review=review,
        draft=draft,
        note=note,
        db_path=db_path,
    )
