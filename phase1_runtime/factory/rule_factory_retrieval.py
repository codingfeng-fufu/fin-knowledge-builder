from __future__ import annotations

from pathlib import Path
from typing import Any

from ..registry.registry_store import DEFAULT_DB_PATH
from ..runtime_flags import runtime_rules_disabled
from .rule_factory_publish_utils import asset_type_from_rule_kind, build_published_rule_payload
from .rule_factory_store import ensure_rule_factory_db, list_rule_versions
from ..schema import Rule


def materialize_rule_from_version(version: dict[str, Any]) -> Rule:
    payload = version['payload']
    rule_payload = payload.get('rule')
    if not isinstance(rule_payload, dict):
        draft = payload.get('draft')
        if not isinstance(draft, dict):
            raise ValueError(f"rule_version payload missing draft/rule: {version['rule_version_id']}")
        rule_payload = build_published_rule_payload(
            draft=draft,
            review=payload.get('review'),
            version_label=version['version_label'],
            status='published',
        )

    normalized = dict(rule_payload)
    normalized['status'] = 'published'
    normalized['version'] = version['version_label']
    return Rule.from_dict(normalized)


def retrieval_asset_from_version(version: dict[str, Any]) -> dict[str, Any]:
    payload = version['payload']
    rule_payload = payload.get('rule')
    if not isinstance(rule_payload, dict):
        draft = payload.get('draft')
        if not isinstance(draft, dict):
            raise ValueError(f"rule_version payload missing draft/rule: {version['rule_version_id']}")
        rule_payload = build_published_rule_payload(
            draft=draft,
            review=payload.get('review'),
            version_label=version['version_label'],
            status='published',
        )
    draft_payload = payload.get('draft', {}).get('payload', {}) if isinstance(payload.get('draft'), dict) else {}
    rule_kind = rule_payload.get('rule_kind') or draft_payload.get('rule_kind') or 'composite'
    return {
        'asset_type': payload.get('asset_type') or draft_payload.get('asset_type') or asset_type_from_rule_kind(rule_kind),
        'asset_id': payload.get('asset_id') or draft_payload.get('asset_id') or version['rule_id'],
        'rule_id': version['rule_id'],
        'rule_kind': rule_kind,
        'rule_family': rule_payload.get('rule_family') or draft_payload.get('rule_family') or version['rule_id'],
        'version_label': version['version_label'],
        'status': version['status'],
        'change_type': payload.get('change_type') or draft_payload.get('change_type') or 'patch',
        'source_trace_ids': payload.get('source_trace_ids') or draft_payload.get('source_trace_ids', []),
        'based_on_asset_ids': payload.get('based_on_asset_ids') or draft_payload.get('based_on_asset_ids', []),
        'supersedes_rule_version_id': payload.get('supersedes_rule_version_id'),
        'trigger': rule_payload.get('trigger'),
        'applicability': rule_payload.get('applicability'),
        'composition': rule_payload.get('composition'),
        'source_validation': payload.get('source_validation'),
        'rule': rule_payload,
    }


def build_retrieval_asset_view(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    latest_by_rule_id: dict[str, dict[str, Any]] = {}
    for version in list_rule_versions(db_path=db_path):
        if version['status'] != 'published':
            continue
        latest_by_rule_id[version['rule_id']] = version
    assets = [retrieval_asset_from_version(version) for version in latest_by_rule_id.values()]
    return {
        'db_path': str(Path(db_path).resolve()),
        'asset_count': len(assets),
        'assets': assets,
    }


def list_published_rules(db_path: str | Path = DEFAULT_DB_PATH) -> list[Rule]:
    asset_view = build_retrieval_asset_view(db_path=db_path)
    return [Rule.from_dict({**asset['rule'], 'status': 'published', 'version': asset['version_label']}) for asset in asset_view['assets']]


def merge_rules_for_runtime(
    base_rules: list[Rule],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[Rule]:
    if runtime_rules_disabled():
        return []
    merged: dict[str, Rule] = {rule.rule_id: rule for rule in base_rules}
    asset_view = build_retrieval_asset_view(db_path=db_path)
    for asset in asset_view['assets']:
        merged[asset['rule_id']] = Rule.from_dict({**asset['rule'], 'status': 'published', 'version': asset['version_label']})
    return list(merged.values())
