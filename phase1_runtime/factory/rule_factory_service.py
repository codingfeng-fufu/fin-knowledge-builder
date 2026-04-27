from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from ..datasets import import_dataset_dir
from ..registry.registry_store import DEFAULT_DB_PATH
from ..retrieval.rule_graph_store import (
    collect_active_rules_for_rule_graph,
    load_or_build_rule_graph_artifacts,
    rebuild_active_rule_graph_artifacts,
    resolve_rule_graph_output_dir,
)
from .rule_factory_feedback import (
    classify_feedback,
    draft_action_from_feedback,
    list_feedback_service,
    promote_feedback_to_draft,
    record_feedback,
)
from .rule_factory_publish_utils import asset_type_from_rule_kind
from .rule_factory_review_flow import (
    approve_review,
    create_review_for_draft,
    get_review,
    list_reviews,
    reject_review,
)
from .rule_factory_retrieval import build_retrieval_asset_view, list_published_rules, merge_rules_for_runtime
from .rule_factory_store import (
    ensure_rule_factory_db,
    get_candidate_rule_draft,
    get_case_record,
    insert_candidate_rule_draft,
    list_candidate_rule_drafts,
    list_case_records,
    list_case_rule_links,
    list_rollback_records,
    list_rule_versions,
    get_rule_version,
    insert_rollback_record,
    update_rule_version_status,
    upsert_case_record,
)
from .rule_factory_workspace import get_workspace_run_service, list_workspace_runs_service, record_workspace_run


def _retrieval_model_defaults() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    dense_local = root / 'local_models' / 'BAAI__bge-base-zh-v1.5'
    rerank_local = root / 'local_models' / 'BAAI__bge-reranker-base'
    return {
        'dense': {
            'model_name': os.getenv('PHASE1_DENSE_MODEL', str(dense_local)),
            'fallback_model_name': os.getenv('PHASE1_DENSE_FALLBACK_MODEL', 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'),
        },
        'cross_rerank': {
            'model_name': os.getenv('PHASE1_RERANK_MODEL', str(rerank_local)),
            'fallback_model_name': os.getenv('PHASE1_RERANK_FALLBACK_MODEL', 'cross-encoder/ms-marco-MiniLM-L-6-v2'),
        },
    }


def ingest_case_from_dataset(
    dataset_dir: str | Path,
    source: str = 'dataset_import',
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    imported = import_dataset_dir(dataset_dir)
    case = imported.case_record
    payload = {
        'case_record': case.to_dict(),
        'dataset_id': imported.simulation_dataset.dataset_id,
        'scenario_name': imported.simulation_dataset.scenario_name,
        'dataset_dir': str(imported.dataset_dir),
        'validation_summary': imported.validation_summary,
        'linked_rule_ids': case.linked_rule_ids,
        'source_trace_id': imported.execution_trace.trace_id,
    }
    return upsert_case_record(
        case_id=case.case_id,
        dataset_id=imported.simulation_dataset.dataset_id,
        scenario_name=imported.simulation_dataset.scenario_name,
        dataset_dir=str(imported.dataset_dir),
        title=case.title,
        question_text=case.question.question_text,
        review_status=case.review_status,
        source=source,
        payload=payload,
        db_path=db_path,
    )


def list_cases(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_case_records(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'case_count': len(items),
        'cases': items,
    }


def get_case(case_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_case_record(case_id, db_path=db_path)


def generate_candidate_rule_draft(
    case_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    case_row = get_case_record(case_id, db_path=db_path)
    dataset_dir = case_row['dataset_dir']
    imported = import_dataset_dir(dataset_dir)
    source_rule_id = None
    if imported.case_record.linked_rule_ids:
        source_rule_id = imported.case_record.linked_rule_ids[0]
    if source_rule_id is None:
        source_rule_id = imported.rule_pool[0].rule_id
    source_rule = next((rule for rule in imported.rule_pool if rule.rule_id == source_rule_id), imported.rule_pool[0])

    draft_id = f'draft_{uuid4().hex[:12]}'
    source_rule_payload = source_rule.to_dict()
    rule_kind = source_rule_payload.get('rule_kind', 'composite')
    payload = {
        'draft_id': draft_id,
        'case_id': case_id,
        'proposed_rule_id': source_rule.rule_id,
        'name': source_rule.name,
        'status': 'draft',
        'asset_type': asset_type_from_rule_kind(rule_kind),
        'asset_id': source_rule.rule_id,
        'change_type': 'patch',
        'source_trace_ids': [imported.execution_trace.trace_id],
        'based_on_asset_ids': [source_rule.rule_id],
        'rule_kind': rule_kind,
        'rule_family': source_rule_payload.get('rule_family', source_rule.rule_id),
        'trigger': source_rule_payload['trigger'],
        'applicability': source_rule_payload['applicability'],
        'inputs': source_rule_payload['inputs'],
        'steps': source_rule_payload['steps'],
        'outputs': source_rule_payload['outputs'],
        'validators': source_rule_payload['validators'],
        'embedding_backend': case_row.get('payload', {}).get('embedding_backend', {}),
        'provenance': {
            'source_case_id': case_id,
            'source_dataset_id': imported.simulation_dataset.dataset_id,
            'source_rule_id': source_rule.rule_id,
            'review_status': 'pending_review',
        },
    }
    if source_rule_payload.get('composition') is not None:
        payload['composition'] = source_rule_payload['composition']
    return insert_candidate_rule_draft(
        draft_id=draft_id,
        case_id=case_id,
        proposed_rule_id=source_rule.rule_id,
        source_rule_id=source_rule.rule_id,
        status='draft',
        payload=payload,
        db_path=db_path,
    )


def list_rule_drafts(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_candidate_rule_drafts(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'draft_count': len(items),
        'drafts': items,
    }


def get_rule_draft(draft_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_candidate_rule_draft(draft_id, db_path=db_path)


def list_rule_versions_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_rule_versions(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'rule_version_count': len(items),
        'rule_versions': items,
    }


def _community_tree_node(communities_by_id: dict[str, Any], community_id: str) -> dict[str, Any]:
    community = communities_by_id[community_id]
    return {
        'community_id': community.community_id,
        'level': community.level,
        'parent_community_id': community.parent_community_id,
        'child_community_ids': list(community.child_community_ids),
        'rule_ids': list(community.rule_ids),
        'meta_rule': community.meta_rule.to_dict(),
        'report': community.report.to_dict(),
        'metadata': dict(community.metadata),
        'children': [_community_tree_node(communities_by_id, child_id) for child_id in community.child_community_ids],
    }


def get_rule_version_service(rule_version_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return get_rule_version(rule_version_id, db_path=db_path)


def rollback_rule_version_service(
    rule_version_id: str,
    reason: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    version = get_rule_version(rule_version_id, db_path=db_path)
    existing_rollbacks = [item for item in list_rollback_records(db_path=db_path) if item['rule_version_id'] == rule_version_id]
    if version['status'] == 'rolled_back' and existing_rollbacks:
        return {
            'rule_version': version,
            'rollback': existing_rollbacks[-1],
            'rule_graph_artifacts': rebuild_active_rule_graph_artifacts(db_path=db_path),
        }
    updated_version = update_rule_version_status(rule_version_id, 'rolled_back', db_path=db_path)
    rollback = insert_rollback_record(
        rollback_id=f'rollback_{uuid4().hex[:12]}',
        rule_version_id=rule_version_id,
        rule_id=version['rule_id'],
        reason=reason,
        db_path=db_path,
    )
    return {
        'rule_version': updated_version,
        'rollback': rollback,
        'rule_graph_artifacts': rebuild_active_rule_graph_artifacts(db_path=db_path),
    }


def list_case_rule_links_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_case_rule_links(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'link_count': len(items),
        'links': items,
    }


def list_rollbacks_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    items = list_rollback_records(db_path=db_path)
    return {
        'db_path': str(Path(db_path).resolve()),
        'rollback_count': len(items),
        'rollbacks': items,
    }


def retrieval_asset_view_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    return build_retrieval_asset_view(db_path=db_path)


def rule_graph_view_service(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_rule_factory_db(db_path)
    rules = collect_active_rules_for_rule_graph(db_path=db_path)
    output_dir = resolve_rule_graph_output_dir(db_path=db_path)
    index, rag_catalog, cache_metadata = load_or_build_rule_graph_artifacts(rules, output_dir=output_dir)
    communities_by_id = index.communities_by_id
    roots = [_community_tree_node(communities_by_id, community.community_id) for community in index.root_communities]
    reports = [
        {
            'community_id': community.community_id,
            'level': community.level,
            'title': community.report.title,
            'summary': community.report.summary,
            'findings': list(community.report.findings),
            'focus_terms': list(community.report.focus_terms),
            'representative_rules': list(community.report.representative_rules),
            'meta_rule': community.meta_rule.to_dict(),
        }
        for community in index.communities
    ]
    return {
        'db_path': str(Path(db_path).resolve()),
        'output_dir': str(Path(output_dir).resolve()),
        'artifact_root': cache_metadata['artifact_root'],
        'fingerprint': cache_metadata['fingerprint'],
        'cache_hit': cache_metadata['cache_hit'],
        'manifest': cache_metadata['manifest'],
        'community_count': len(index.communities),
        'root_community_count': len(index.root_communities),
        'leaf_community_count': len(index.leaf_communities),
        'rule_count': len(index.records),
        'rag_passage_count': len(rag_catalog),
        'graph_backend': index.metadata.get('graph_backend'),
        'hierarchy_depth': index.metadata.get('hierarchy_depth', 0),
        'community_by_rule_id': dict(index.community_by_rule_id),
        'retrieval_models': _retrieval_model_defaults(),
        'roots': roots,
        'reports': reports,
    }
