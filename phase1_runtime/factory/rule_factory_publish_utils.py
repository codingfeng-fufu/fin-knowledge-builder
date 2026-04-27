from __future__ import annotations

from typing import Any

from .rule_factory_errors import RuleFactoryError


def asset_type_from_rule_kind(rule_kind: str) -> str:
    if rule_kind == 'atomic':
        return 'atomic_rule'
    return 'composite_rule'


def normalize_review_status(review: dict[str, Any] | None) -> str:
    if review is None:
        return 'approved'
    status = review.get('status')
    if status == 'rejected':
        return 'rejected'
    if status == 'unreviewed':
        return 'unreviewed'
    return 'approved'


def build_published_rule_payload(
    draft: dict[str, Any],
    review: dict[str, Any] | None,
    version_label: str,
    status: str = 'published',
) -> dict[str, Any]:
    draft_payload = draft['payload']
    reviewer = 'rule_factory'
    reviewed_at = draft.get('updated_at') or draft.get('created_at') or ''
    review_status = normalize_review_status(review)
    if review is not None:
        reviewer = review.get('assignee') or reviewer
        reviewed_at = review.get('updated_at') or review.get('created_at') or reviewed_at

    rule_kind = draft_payload.get('rule_kind', 'composite')
    payload = {
        'rule_id': draft['proposed_rule_id'],
        'name': draft_payload['name'],
        'status': status,
        'version': version_label,
        'rule_kind': rule_kind,
        'rule_family': draft_payload.get('rule_family', draft['proposed_rule_id']),
        'asset_type': draft_payload.get('asset_type', asset_type_from_rule_kind(rule_kind)),
        'asset_id': draft_payload.get('asset_id', draft['proposed_rule_id']),
        'change_type': draft_payload.get('change_type', 'patch'),
        'source_trace_ids': list(draft_payload.get('source_trace_ids', [])),
        'based_on_asset_ids': list(draft_payload.get('based_on_asset_ids', [])),
        'trigger': draft_payload['trigger'],
        'applicability': draft_payload['applicability'],
        'inputs': draft_payload['inputs'],
        'steps': draft_payload['steps'],
        'outputs': draft_payload['outputs'],
        'validators': draft_payload['validators'],
        'provenance': {
            'source_cases': [draft['case_id']],
            'review': {
                'review_status': review_status,
                'reviewer': reviewer,
                'reviewed_at': reviewed_at,
            },
        },
    }
    if draft_payload.get('composition') is not None:
        payload['composition'] = draft_payload['composition']
    return payload


def validate_draft_provenance(draft: dict[str, Any]) -> dict[str, Any]:
    provenance = draft['payload'].get('provenance')
    if not isinstance(provenance, dict):
        raise RuleFactoryError(f"draft missing provenance: {draft['draft_id']}")

    required_fields = ('source_case_id', 'source_dataset_id', 'source_rule_id')
    missing = [field for field in required_fields if not provenance.get(field)]
    if missing:
        raise RuleFactoryError(f"draft provenance missing fields {missing}: {draft['draft_id']}")
    if provenance['source_case_id'] != draft['case_id']:
        raise RuleFactoryError(f"draft provenance/source case mismatch: {draft['draft_id']}")
    return provenance
