from __future__ import annotations

from .rule_factory_errors import RuleFactoryError


def approve_review(*args, **kwargs):
    from .rule_factory_review_flow import approve_review as _fn

    return _fn(*args, **kwargs)


def create_review_for_draft(*args, **kwargs):
    from .rule_factory_review_flow import create_review_for_draft as _fn

    return _fn(*args, **kwargs)


def generate_candidate_rule_draft(*args, **kwargs):
    from .rule_factory_service import generate_candidate_rule_draft as _fn

    return _fn(*args, **kwargs)


def get_case(*args, **kwargs):
    from .rule_factory_service import get_case as _fn

    return _fn(*args, **kwargs)


def get_feedback_service(*args, **kwargs):
    from .rule_factory_feedback import get_feedback_service as _fn

    return _fn(*args, **kwargs)


def get_review(*args, **kwargs):
    from .rule_factory_review_flow import get_review as _fn

    return _fn(*args, **kwargs)


def get_rule_draft(*args, **kwargs):
    from .rule_factory_service import get_rule_draft as _fn

    return _fn(*args, **kwargs)


def get_rule_version_service(*args, **kwargs):
    from .rule_factory_service import get_rule_version_service as _fn

    return _fn(*args, **kwargs)


def get_workspace_run_service(*args, **kwargs):
    from .rule_factory_workspace import get_workspace_run_service as _fn

    return _fn(*args, **kwargs)


def ingest_case_from_dataset(*args, **kwargs):
    from .rule_factory_service import ingest_case_from_dataset as _fn

    return _fn(*args, **kwargs)


def list_case_rule_links_service(*args, **kwargs):
    from .rule_factory_service import list_case_rule_links_service as _fn

    return _fn(*args, **kwargs)


def list_cases(*args, **kwargs):
    from .rule_factory_service import list_cases as _fn

    return _fn(*args, **kwargs)


def list_feedback_service(*args, **kwargs):
    from .rule_factory_feedback import list_feedback_service as _fn

    return _fn(*args, **kwargs)


def list_reviews(*args, **kwargs):
    from .rule_factory_review_flow import list_reviews as _fn

    return _fn(*args, **kwargs)


def list_rollbacks_service(*args, **kwargs):
    from .rule_factory_service import list_rollbacks_service as _fn

    return _fn(*args, **kwargs)


def list_rule_drafts(*args, **kwargs):
    from .rule_factory_service import list_rule_drafts as _fn

    return _fn(*args, **kwargs)


def list_rule_versions_service(*args, **kwargs):
    from .rule_factory_service import list_rule_versions_service as _fn

    return _fn(*args, **kwargs)


def list_workspace_runs_service(*args, **kwargs):
    from .rule_factory_workspace import list_workspace_runs_service as _fn

    return _fn(*args, **kwargs)


def merge_rules_for_runtime(*args, **kwargs):
    from .rule_factory_retrieval import merge_rules_for_runtime as _fn

    return _fn(*args, **kwargs)


def promote_feedback_to_draft(*args, **kwargs):
    from .rule_factory_feedback import promote_feedback_to_draft as _fn

    return _fn(*args, **kwargs)


def record_feedback(*args, **kwargs):
    from .rule_factory_feedback import record_feedback as _fn

    return _fn(*args, **kwargs)


def record_workspace_run(*args, **kwargs):
    from .rule_factory_workspace import record_workspace_run as _fn

    return _fn(*args, **kwargs)


def reject_review(*args, **kwargs):
    from .rule_factory_review_flow import reject_review as _fn

    return _fn(*args, **kwargs)


def retrieval_asset_view_service(*args, **kwargs):
    from .rule_factory_service import retrieval_asset_view_service as _fn

    return _fn(*args, **kwargs)


def rule_graph_view_service(*args, **kwargs):
    from .rule_factory_service import rule_graph_view_service as _fn

    return _fn(*args, **kwargs)


def rollback_rule_version_service(*args, **kwargs):
    from .rule_factory_service import rollback_rule_version_service as _fn

    return _fn(*args, **kwargs)


__all__ = [
    "RuleFactoryError",
    "approve_review",
    "create_review_for_draft",
    "generate_candidate_rule_draft",
    "get_case",
    "get_feedback_service",
    "get_review",
    "get_rule_draft",
    "get_rule_version_service",
    "get_workspace_run_service",
    "ingest_case_from_dataset",
    "list_case_rule_links_service",
    "list_cases",
    "list_feedback_service",
    "list_reviews",
    "list_rollbacks_service",
    "list_rule_drafts",
    "list_rule_versions_service",
    "list_workspace_runs_service",
    "merge_rules_for_runtime",
    "promote_feedback_to_draft",
    "record_feedback",
    "record_workspace_run",
    "reject_review",
    "retrieval_asset_view_service",
    "rule_graph_view_service",
    "rollback_rule_version_service",
]
