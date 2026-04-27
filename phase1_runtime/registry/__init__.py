from __future__ import annotations

from .registry_store import DEFAULT_DB_PATH, ensure_registry_db


def register_dataset(*args, **kwargs):
    from .registry_service import register_dataset as _fn

    return _fn(*args, **kwargs)


def list_registered_datasets(*args, **kwargs):
    from .registry_service import list_registered_datasets as _fn

    return _fn(*args, **kwargs)


def get_registered_dataset(*args, **kwargs):
    from .registry_service import get_registered_dataset as _fn

    return _fn(*args, **kwargs)


def run_registered_workflow_sync(*args, **kwargs):
    from .registry_service import run_registered_workflow_sync as _fn

    return _fn(*args, **kwargs)


def submit_registered_workflow(*args, **kwargs):
    from .registry_service import submit_registered_workflow as _fn

    return _fn(*args, **kwargs)


def list_workflow_runs(*args, **kwargs):
    from .registry_service import list_workflow_runs as _fn

    return _fn(*args, **kwargs)


def get_workflow_run(*args, **kwargs):
    from .registry_service import get_workflow_run as _fn

    return _fn(*args, **kwargs)


def mark_workflow_run_running(*args, **kwargs):
    from .registry_service import mark_workflow_run_running as _fn

    return _fn(*args, **kwargs)


def complete_registered_workflow_run(*args, **kwargs):
    from .registry_service import complete_registered_workflow_run as _fn

    return _fn(*args, **kwargs)


__all__ = [
    "DEFAULT_DB_PATH",
    "complete_registered_workflow_run",
    "ensure_registry_db",
    "get_registered_dataset",
    "get_workflow_run",
    "list_registered_datasets",
    "list_workflow_runs",
    "mark_workflow_run_running",
    "register_dataset",
    "run_registered_workflow_sync",
    "submit_registered_workflow",
]
