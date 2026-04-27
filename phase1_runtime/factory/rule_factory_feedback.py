from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ..registry.registry_store import DEFAULT_DB_PATH
from .rule_factory_draft_builder import (
    build_draft_payload_from_feedback,
    existing_draft_for_feedback,
)
from .rule_factory_publish_utils import asset_type_from_rule_kind
from .rule_factory_store import (
    ensure_rule_factory_db,
    get_feedback_record,
    insert_candidate_rule_draft,
    insert_feedback_record,
    list_feedback_records,
)


def feedback_semantics(feedback_type: str) -> dict[str, str]:
    mapping = {
        'missed_rule': {'classification': 'coverage_gap', 'recommended_action': 'create_new_atomic_rule'},
        'composition_failure': {'classification': 'composition_gap', 'recommended_action': 'create_or_patch_composite_rule'},
        'stable_composition': {'classification': 'composition_candidate', 'recommended_action': 'create_or_patch_composite_rule'},
        'wrong_rule_selected': {'classification': 'retrieval_gap', 'recommended_action': 'patch_rule_scope'},
        'insufficient_evidence': {'classification': 'evidence_gap', 'recommended_action': 'patch_evidence_pattern'},
        'bad_final_answer': {'classification': 'quality_gap', 'recommended_action': 'patch_existing_rule_scope'},
    }
    return mapping.get(feedback_type, {'classification': 'observation', 'recommended_action': 'triage'})


def _apply_explicit_recommended_action(
    *,
    semantics: dict[str, str],
    explicit_recommended_action: str | None,
) -> tuple[dict[str, str], str | None]:
    if explicit_recommended_action not in {
        'create_new_atomic_rule',
        'create_or_patch_composite_rule',
        'patch_rule_scope',
        'patch_existing_rule_scope',
        'patch_evidence_pattern',
    }:
        return semantics, None

    updated = dict(semantics)
    updated['recommended_action'] = explicit_recommended_action
    if explicit_recommended_action == 'create_or_patch_composite_rule':
        updated['classification'] = 'composition_candidate'
    elif explicit_recommended_action == 'create_new_atomic_rule':
        updated['classification'] = 'coverage_gap'
    elif explicit_recommended_action == 'patch_evidence_pattern':
        updated['classification'] = 'evidence_gap'
    else:
        updated['classification'] = 'scope_gap'
    return updated, 'exploration_recommended_action'


def _recommended_action_from_source_payload(source_payload: dict[str, Any]) -> str | None:
    direct = source_payload.get('recommended_action')
    if isinstance(direct, str) and direct:
        return direct
    exploration_runtime = source_payload.get('exploration_runtime')
    if not isinstance(exploration_runtime, dict):
        return None
    candidate_drafts = exploration_runtime.get('candidate_rule_drafts')
    if not isinstance(candidate_drafts, list) or not candidate_drafts:
        return None
    candidate = candidate_drafts[0]
    if not isinstance(candidate, dict):
        return None
    action = candidate.get('recommended_action')
    return str(action) if isinstance(action, str) and action else None


def draft_action_from_feedback(
    feedback_type: str,
    *,
    route_decision: str,
    rule_ids: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_payload = {} if payload is None else dict(payload)
    semantics = dict(feedback_semantics(feedback_type))
    rule_ids = [] if rule_ids is None else list(rule_ids)
    missing_fact_keys = list(source_payload.get('missing_fact_keys', [])) if isinstance(source_payload.get('missing_fact_keys', []), list) else []
    parser_status = source_payload.get('parser_status')
    decision_reason = 'default_mapping'
    explicit_recommended_action = _recommended_action_from_source_payload(source_payload)
    semantics, override_reason = _apply_explicit_recommended_action(
        semantics=semantics,
        explicit_recommended_action=explicit_recommended_action,
    )
    if override_reason is not None:
        decision_reason = override_reason

    if decision_reason != 'exploration_recommended_action' and feedback_type == 'missed_rule' and rule_ids:
        if parser_status in {'parsed_complete', 'parsed_with_defaults'} and not missing_fact_keys:
            semantics['classification'] = 'scope_gap'
            semantics['recommended_action'] = 'patch_existing_rule_scope'
            decision_reason = 'known_family_without_missing_facts'
        elif source_payload.get('matched_rule_id'):
            semantics['classification'] = 'scope_gap'
            semantics['recommended_action'] = 'patch_existing_rule_scope'
            decision_reason = 'matched_rule_but_not_reused'
    elif decision_reason != 'exploration_recommended_action' and feedback_type in {'wrong_rule_selected', 'bad_final_answer'} and rule_ids:
        decision_reason = 'existing_asset_should_be_patched'
    elif decision_reason != 'exploration_recommended_action' and feedback_type == 'insufficient_evidence' and rule_ids:
        decision_reason = 'existing_asset_needs_evidence_patch'
    elif decision_reason != 'exploration_recommended_action' and feedback_type in {'composition_failure', 'stable_composition'}:
        if len(rule_ids) == 1:
            semantics['classification'] = 'composition_patch'
            semantics['recommended_action'] = 'patch_existing_rule_scope'
            decision_reason = 'single_composite_should_be_patched'
        else:
            decision_reason = 'multi_rule_composition_candidate'
    elif decision_reason != 'exploration_recommended_action' and route_decision == 'direct_match' and rule_ids and semantics['recommended_action'] == 'create_new_atomic_rule':
        semantics['classification'] = 'scope_gap'
        semantics['recommended_action'] = 'patch_existing_rule_scope'
        decision_reason = 'direct_match_should_patch_existing_asset'

    return {
        'classification': semantics['classification'],
        'recommended_action': semantics['recommended_action'],
        'decision_reason': decision_reason,
        'source_payload': source_payload,
    }


def record_feedback(
    trace_id: str,
    route_decision: str,
    feedback_type: str,
    rule_ids: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    case_id: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    normalized_payload = draft_action_from_feedback(
        feedback_type,
        route_decision=route_decision,
        rule_ids=[] if rule_ids is None else list(rule_ids),
        payload={} if payload is None else dict(payload),
    )
    return insert_feedback_record(
        feedback_id=f'feedback_{uuid4().hex[:12]}',
        trace_id=trace_id,
        case_id=case_id,
        route_decision=route_decision,
        feedback_type=feedback_type,
        rule_ids=[] if rule_ids is None else list(rule_ids),
        payload=normalized_payload,
        db_path=db_path,
    )


def list_feedback_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_feedback_records(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'feedback_count': len(items),
        'feedback': items,
    }


def get_feedback_service(feedback_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_feedback_record(feedback_id, db_path=db_path)


def classify_feedback(feedback_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    feedback = get_feedback_record(feedback_id, db_path=db_path)
    payload = feedback.get('payload', {})
    return {
        'feedback_id': feedback['feedback_id'],
        'trace_id': feedback['trace_id'],
        'case_id': feedback['case_id'],
        'feedback_type': feedback['feedback_type'],
        'classification': payload.get('classification', 'observation'),
        'recommended_action': payload.get('recommended_action', 'triage'),
        'decision_reason': payload.get('decision_reason', 'default_mapping'),
        'rule_ids': feedback.get('rule_ids', []),
        'source_payload': payload.get('source_payload', {}),
    }


def promote_feedback_to_draft(
    feedback_id: str,
    *,
    asset_type_from_rule_kind_fn=asset_type_from_rule_kind,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    feedback = get_feedback_record(feedback_id, db_path=db_path)
    existing_draft = existing_draft_for_feedback(feedback_id, db_path=db_path)
    if existing_draft is not None:
        return {
            'feedback': feedback,
            'classification': classify_feedback(feedback_id, db_path=db_path),
            'draft': existing_draft,
            'reused_existing_draft': True,
        }
    proposed_rule_id, source_rule_id, payload = build_draft_payload_from_feedback(
        feedback,
        asset_type_from_rule_kind_fn,
        db_path=db_path,
    )
    draft = insert_candidate_rule_draft(
        draft_id=payload['draft_id'],
        case_id=feedback['case_id'],
        proposed_rule_id=proposed_rule_id,
        source_rule_id=source_rule_id,
        status='draft',
        payload=payload,
        db_path=db_path,
    )
    return {
        'feedback': feedback,
        'classification': classify_feedback(feedback_id, db_path=db_path),
        'draft': draft,
        'reused_existing_draft': False,
    }
