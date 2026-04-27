from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from ..datasets import import_dataset_dir
from ..registry.registry_store import DEFAULT_DB_PATH
from ..schema import Rule, load_rule
from .rule_factory_errors import RuleFactoryError
from .rule_factory_retrieval import list_published_rules
from .rule_factory_store import (
    get_case_record,
    list_candidate_rule_drafts,
)


def _resolve_source_dataset_id(feedback: dict[str, Any], db_path: str | Path) -> str:
    source_dataset_id = 'feedback_unlinked'
    try:
        case_row = get_case_record(feedback['case_id'], db_path=db_path)
    except FileNotFoundError:
        return source_dataset_id

    dataset_dir = str(case_row.get('dataset_dir', ''))
    if dataset_dir.startswith('workspace://'):
        return source_dataset_id
    try:
        imported = import_dataset_dir(dataset_dir)
    except Exception:
        return source_dataset_id
    return imported.simulation_dataset.dataset_id


def _source_payload(feedback: dict[str, Any]) -> dict[str, Any]:
    payload = feedback.get('payload', {})
    return payload.get('source_payload', {}) if isinstance(payload.get('source_payload', {}), dict) else {}


def _runtime_metadata_from_feedback(feedback: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    source_payload = _source_payload(feedback)
    embedding_backend = (
        source_payload.get('embedding_backend')
        or feedback.get('payload', {}).get('embedding_backend')
        or {}
    )
    runtime_skill_spec_preview = (
        source_payload.get('runtime_skill_spec_preview')
        or feedback.get('payload', {}).get('runtime_skill_spec_preview')
        or {}
    )
    return dict(embedding_backend), dict(runtime_skill_spec_preview)


def _imported_case_bundle_for_feedback(feedback: dict[str, Any], db_path: str | Path) -> tuple[dict[str, Any], Any] | tuple[None, None]:
    if not feedback.get('case_id'):
        return None, None
    try:
        case_row = get_case_record(feedback['case_id'], db_path=db_path)
    except FileNotFoundError:
        return None, None
    dataset_dir = str(case_row.get('dataset_dir', ''))
    if dataset_dir.startswith('workspace://'):
        return case_row, None
    try:
        imported = import_dataset_dir(dataset_dir)
    except Exception:
        return case_row, None
    return case_row, imported


def _resolve_draft_target(
    *,
    feedback: dict[str, Any],
    recommended_action: str,
    template_rule_id: str,
    template_payload: dict[str, Any],
    asset_type_from_rule_kind_fn,
) -> tuple[str, str, str, str, str | None]:
    if recommended_action == 'create_new_atomic_rule':
        return (
            'atomic_rule',
            'atomic',
            'new',
            f'atomic.generated.{feedback["feedback_id"]}',
            template_rule_id,
        )
    if recommended_action == 'create_or_patch_composite_rule':
        feedback_rule_ids = list(feedback.get('rule_ids', []))
        if len(feedback_rule_ids) > 1:
            return (
                'composite_rule',
                'composite',
                'new',
                f'composite.generated.{feedback["feedback_id"]}',
                template_rule_id,
            )
        if len(feedback_rule_ids) == 1 and template_payload.get('rule_kind', 'composite') == 'composite':
            return (
                'composite_rule',
                'composite',
                'patch',
                feedback_rule_ids[0],
                feedback_rule_ids[0],
            )
        return (
            'composite_rule',
            'composite',
            'new',
            f'composite.generated.{feedback["feedback_id"]}',
            template_rule_id,
        )
    if recommended_action in {'patch_rule_scope', 'patch_existing_rule_scope', 'patch_evidence_pattern'}:
        target_rule_id = feedback['rule_ids'][0] if feedback.get('rule_ids') else template_rule_id
        return (
            template_payload.get('asset_type', asset_type_from_rule_kind_fn(template_payload.get('rule_kind', 'composite'))),
            template_payload.get('rule_kind', 'composite'),
            'patch',
            target_rule_id,
            target_rule_id,
        )
    raise RuleFactoryError(f'feedback recommended_action not supported for draft promotion yet: {recommended_action}')


def _base_draft_payload(
    *,
    feedback: dict[str, Any],
    classification: str,
    recommended_action: str,
    source_rule_id: str | None,
    proposed_rule_id: str,
    source_dataset_id: str,
    asset_type: str,
    rule_kind: str,
    change_type: str,
    template_payload: dict[str, Any],
) -> dict[str, Any]:
    embedding_backend, runtime_skill_spec_preview = _runtime_metadata_from_feedback(feedback)
    return {
        'draft_id': f'draft_{uuid4().hex[:12]}',
        'case_id': feedback['case_id'],
        'proposed_rule_id': proposed_rule_id,
        'name': f'feedback_{classification}_{proposed_rule_id}',
        'status': 'draft',
        'asset_type': asset_type,
        'asset_id': proposed_rule_id,
        'change_type': change_type,
        'source_trace_ids': [feedback['trace_id']],
        'based_on_asset_ids': list(feedback.get('rule_ids', [])),
        'rule_kind': rule_kind,
        'rule_family': template_payload.get('rule_family', template_payload.get('rule_id', proposed_rule_id)),
        'trigger': template_payload['trigger'],
        'applicability': template_payload['applicability'],
        'inputs': template_payload['inputs'],
        'steps': template_payload['steps'],
        'outputs': template_payload['outputs'],
        'validators': template_payload['validators'],
        'feedback_context': {
            'feedback_id': feedback['feedback_id'],
            'classification': classification,
            'recommended_action': recommended_action,
            'decision_reason': feedback.get('payload', {}).get('decision_reason', 'default_mapping'),
            'source_payload': _source_payload(feedback),
        },
        'embedding_backend': embedding_backend,
        'runtime_skill_spec_preview': runtime_skill_spec_preview,
        'provenance': {
            'source_case_id': feedback['case_id'],
            'source_dataset_id': source_dataset_id,
            'source_rule_id': source_rule_id,
            'review_status': 'pending_review',
        },
    }


def _attach_patch_target(payload: dict[str, Any], *, recommended_action: str, proposed_rule_id: str, source_rule_id: str | None) -> None:
    if recommended_action not in {'patch_rule_scope', 'patch_existing_rule_scope', 'patch_evidence_pattern'}:
        return
    payload['patch_target'] = {
        'patch_type': 'evidence_pattern' if recommended_action == 'patch_evidence_pattern' else 'scope',
        'target_asset_id': proposed_rule_id,
        'target_rule_id': source_rule_id,
    }


def _attach_composition_payload(
    payload: dict[str, Any],
    *,
    feedback: dict[str, Any],
    recommended_action: str,
    asset_type: str,
    template_payload: dict[str, Any],
) -> None:
    template_composition = template_payload.get('composition') if isinstance(template_payload.get('composition'), dict) else {}
    if asset_type == 'composite_rule' and (recommended_action == 'create_or_patch_composite_rule' or template_composition):
        source_rule_ids = list(feedback.get('rule_ids', [])) or list(template_composition.get('source_rule_ids', []))
        payload['composition'] = {
            'pattern': _source_payload(feedback).get('composition_pattern')
                or template_composition.get('pattern')
                or 'derive_then_decide',
            'source_rule_ids': source_rule_ids,
            'binding_schema': {
                'feedback_id': feedback['feedback_id'],
                'recommended_action': recommended_action,
            },
        }
        return
    if template_payload.get('composition') is not None:
        payload['composition'] = template_payload['composition']


def _fixture_rule_for_feedback(rule_ids: list[str]) -> Rule | None:
    fixture_dir = Path(__file__).resolve().parents[1] / 'fixtures'
    for rule_path in sorted(fixture_dir.glob('rule*.json')):
        try:
            rule = load_rule(rule_path)
        except Exception:
            continue
        if rule.rule_id in rule_ids:
            return rule
    return None


def _template_rule_for_feedback(feedback: dict[str, Any], db_path: str | Path = DEFAULT_DB_PATH) -> Rule | None:
    preferred_rule_ids = list(feedback.get('rule_ids', []))
    _case_row, imported = _imported_case_bundle_for_feedback(feedback, db_path=db_path)
    if imported is not None:
        for rule_id in preferred_rule_ids:
            for rule in imported.rule_pool:
                if rule.rule_id == rule_id:
                    return rule
        if imported.rule_pool:
            return imported.rule_pool[0]
    published = {rule.rule_id: rule for rule in list_published_rules(db_path=db_path)}
    for rule_id in preferred_rule_ids:
        if rule_id in published:
            return published[rule_id]
    fixture_rule = _fixture_rule_for_feedback(preferred_rule_ids)
    if fixture_rule is not None:
        return fixture_rule
    return next(iter(published.values()), None)


def _synthetic_template_payload_from_exploration(feedback: dict[str, Any]) -> dict[str, Any] | None:
    source_payload = _source_payload(feedback)
    exploration_runtime = source_payload.get('exploration_runtime')
    if not isinstance(exploration_runtime, dict):
        return None
    candidate_drafts = exploration_runtime.get('candidate_rule_drafts')
    if not isinstance(candidate_drafts, list) or not candidate_drafts:
        return None
    candidate = candidate_drafts[0] if isinstance(candidate_drafts[0], dict) else {}
    question_packet_preview = source_payload.get('question_packet_preview', {}) if isinstance(source_payload.get('question_packet_preview', {}), dict) else {}
    question_text = str(source_payload.get('question_text') or '')
    scenario_id = str(source_payload.get('scenario_id') or 'exploration')
    recommended_action = str(feedback.get('payload', {}).get('recommended_action') or '')
    rule_kind = 'atomic' if recommended_action == 'create_new_atomic_rule' else 'composite'
    summary = str(candidate.get('summary') or (exploration_runtime.get('case_draft') or {}).get('summary') or '探索系统生成了一份候选方法。')
    rule_text = str(candidate.get('rule_text') or summary)
    candidate_title = str(candidate.get('rule_title') or candidate.get('draft_type') or f'exploration_{scenario_id}')
    template_rule_id = str(candidate.get('rule_id') or f'exploration.template.{feedback["feedback_id"]}')
    query_signal = question_text[:24].strip() or candidate_title
    return {
        'rule_id': template_rule_id,
        'name': candidate_title,
        'rule_kind': rule_kind,
        'rule_family': scenario_id,
        'trigger': {
            'query_signals': [query_signal],
            'question_types': list(question_packet_preview.get('question_types', ['analysis_query'])),
            'intents': list(question_packet_preview.get('intents', ['extract', 'summarize'])),
        },
        'applicability': {
            'document_types': list(question_packet_preview.get('document_types', ['report'])),
            'scope': summary,
            'non_scope': '这是探索阶段生成的临时方法草稿，尚未正式接入。',
        },
        'inputs': {
            'required': [],
            'optional': [],
        },
        'steps': [
            {
                'step_id': 'build_exploration_answer',
                'type': 'explain',
                'goal': rule_text,
                'depends_on': [],
                'io': {
                    'inputs': [],
                    'outputs': [
                        {'key': 'answer_text', 'type': 'string', 'description': '探索性答案'},
                        {'key': 'decision', 'type': 'string', 'description': '探索性决策'},
                        {'key': 'evidence_refs', 'type': 'array', 'description': '原文出处'},
                    ],
                },
                'executor': {
                    'mode': 'llm',
                    'allowed_tools': [],
                },
                'constraints': {
                    'must_use_evidence': True,
                },
            }
        ],
        'outputs': {
            'answer_schema': {
                'type': 'object',
                'required': ['answer_text', 'decision', 'evidence_refs'],
                'properties': {
                    'answer_text': {'type': 'string'},
                    'decision': {'type': 'string'},
                    'evidence_refs': {'type': 'array'},
                },
            },
            'must_include': ['answer_text', 'decision', 'evidence_refs'],
        },
        'validators': [
            {
                'validator_id': 'schema.validate',
                'target': 'final',
                'severity': 'error',
            },
            {
                'validator_id': 'evidence.required',
                'target': 'final',
                'severity': 'error',
            },
        ],
    }


def build_draft_payload_from_feedback(
    feedback: dict[str, Any],
    asset_type_from_rule_kind_fn,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[str, str | None, dict[str, Any]]:
    classification = feedback.get('payload', {}).get('classification', 'observation')
    recommended_action = feedback.get('payload', {}).get('recommended_action', 'triage')
    template_rule = _template_rule_for_feedback(feedback, db_path=db_path)
    if template_rule is None:
        synthetic_payload = _synthetic_template_payload_from_exploration(feedback)
        if synthetic_payload is None:
            raise RuleFactoryError(f'feedback cannot be promoted without a template rule: {feedback["feedback_id"]}')
        template_payload = synthetic_payload
        template_rule_id = str(template_payload['rule_id'])
    else:
        template_payload = template_rule.to_dict()
        template_rule_id = template_rule.rule_id

    if not feedback.get('case_id'):
        raise RuleFactoryError(f'feedback missing case_id for draft promotion: {feedback["feedback_id"]}')

    source_dataset_id = _resolve_source_dataset_id(feedback, db_path=db_path)
    asset_type, rule_kind, change_type, proposed_rule_id, source_rule_id = _resolve_draft_target(
        feedback=feedback,
        recommended_action=recommended_action,
        template_rule_id=template_rule_id,
        template_payload=template_payload,
        asset_type_from_rule_kind_fn=asset_type_from_rule_kind_fn,
    )
    payload = _base_draft_payload(
        feedback=feedback,
        classification=classification,
        recommended_action=recommended_action,
        source_rule_id=source_rule_id,
        proposed_rule_id=proposed_rule_id,
        source_dataset_id=source_dataset_id,
        asset_type=asset_type,
        rule_kind=rule_kind,
        change_type=change_type,
        template_payload=template_payload,
    )
    _attach_patch_target(
        payload,
        recommended_action=recommended_action,
        proposed_rule_id=proposed_rule_id,
        source_rule_id=source_rule_id,
    )
    _attach_composition_payload(
        payload,
        feedback=feedback,
        recommended_action=recommended_action,
        asset_type=asset_type,
        template_payload=template_payload,
    )
    return proposed_rule_id, source_rule_id, payload


def existing_draft_for_feedback(feedback_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any] | None:
    for draft in list_candidate_rule_drafts(db_path=db_path):
        payload = draft.get('payload', {})
        if payload.get('feedback_context', {}).get('feedback_id') == feedback_id and draft.get('status') != 'rejected':
            return draft
    return None
