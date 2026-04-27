from __future__ import annotations

from .demo import handle_catalog, handle_replay, handle_run
from .demo_case_service import get_workspace_demo_case, list_workspace_demo_cases
from .mock_data import (
    DEFAULT_SCENARIO_VARIANTS,
    generate_batch_simulation_datasets,
    generate_simulation_dataset,
)
from .mock_data_credit import generate_credit_simulation_dataset


__all__ = [
    "DEFAULT_SCENARIO_VARIANTS",
    "generate_batch_simulation_datasets",
    "generate_credit_simulation_dataset",
    "generate_simulation_dataset",
    "get_workspace_demo_case",
    "handle_catalog",
    "handle_replay",
    "handle_run",
    "list_workspace_demo_cases",
    "run_demo_case",
]


def run_demo_case(*args, **kwargs):
    from .demo_case_runner import run_demo_case as _run_demo_case

    return _run_demo_case(*args, **kwargs)
