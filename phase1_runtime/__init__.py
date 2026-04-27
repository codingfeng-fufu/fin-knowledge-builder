"""Phase 1 runtime prototype for the rule asset platform."""

from .catalog import RuleCatalog
from .replay import load_trace, resolve_trace_path, summarize_trace
from .runtime_core import Phase1Runtime, RuntimeResult
from .schema import QuestionStruct, Rule, load_document_bundle, load_question, load_rule


def build_schema_registry():
    from .contracts import build_schema_registry as _build_schema_registry

    return _build_schema_registry()


def write_formal_schemas(*args, **kwargs):
    from .contracts import write_formal_schemas as _write_formal_schemas

    return _write_formal_schemas(*args, **kwargs)


def generate_simulation_dataset(*args, **kwargs):
    from .tools.mock_data import generate_simulation_dataset as _generate_simulation_dataset

    return _generate_simulation_dataset(*args, **kwargs)


def generate_batch_simulation_datasets(*args, **kwargs):
    from .tools.mock_data import generate_batch_simulation_datasets as _generate_batch_simulation_datasets

    return _generate_batch_simulation_datasets(*args, **kwargs)


def generate_credit_simulation_dataset(*args, **kwargs):
    from .tools.mock_data_credit import generate_credit_simulation_dataset as _generate_credit_simulation_dataset

    return _generate_credit_simulation_dataset(*args, **kwargs)


def validate_dataset_dir(*args, **kwargs):
    from .contracts import validate_dataset_dir as _validate_dataset_dir

    return _validate_dataset_dir(*args, **kwargs)


def write_validation_summary(*args, **kwargs):
    from .contracts import write_validation_summary as _write_validation_summary

    return _write_validation_summary(*args, **kwargs)


def import_dataset_dir(*args, **kwargs):
    from .datasets import import_dataset_dir as _import_dataset_dir

    return _import_dataset_dir(*args, **kwargs)


def summarize_imported_dataset(*args, **kwargs):
    from .datasets import summarize_imported_dataset as _summarize_imported_dataset

    return _summarize_imported_dataset(*args, **kwargs)


def replay_imported_dataset(*args, **kwargs):
    from .datasets import replay_imported_dataset as _replay_imported_dataset

    return _replay_imported_dataset(*args, **kwargs)


def rerun_imported_dataset(*args, **kwargs):
    from .datasets import rerun_imported_dataset as _rerun_imported_dataset

    return _rerun_imported_dataset(*args, **kwargs)


def run_full_workflow(*args, **kwargs):
    from .datasets import run_full_workflow as _run_full_workflow

    return _run_full_workflow(*args, **kwargs)


def handle_request(*args, **kwargs):
    from .api.api_service import handle_request as _handle_request

    return _handle_request(*args, **kwargs)


def create_http_server(*args, **kwargs):
    from .api.api_http import create_server as _create_server

    return _create_server(*args, **kwargs)


def serve_http_api(*args, **kwargs):
    from .api.api_http import serve as _serve

    return _serve(*args, **kwargs)


def ensure_registry_db(*args, **kwargs):
    from .registry import ensure_registry_db as _ensure_registry_db

    return _ensure_registry_db(*args, **kwargs)


def register_dataset(*args, **kwargs):
    from .registry import register_dataset as _register_dataset

    return _register_dataset(*args, **kwargs)


def list_registered_datasets(*args, **kwargs):
    from .registry import list_registered_datasets as _list_registered_datasets

    return _list_registered_datasets(*args, **kwargs)


def get_registered_dataset(*args, **kwargs):
    from .registry import get_registered_dataset as _get_registered_dataset

    return _get_registered_dataset(*args, **kwargs)


def list_workflow_runs(*args, **kwargs):
    from .registry import list_workflow_runs as _list_workflow_runs

    return _list_workflow_runs(*args, **kwargs)


def get_workflow_run(*args, **kwargs):
    from .registry import get_workflow_run as _get_workflow_run

    return _get_workflow_run(*args, **kwargs)


__all__ = [
    "Phase1Runtime",
    "RuntimeResult",
    "QuestionStruct",
    "Rule",
    "RuleCatalog",
    "build_schema_registry",
    "write_formal_schemas",
    "generate_simulation_dataset",
    "generate_batch_simulation_datasets",
    "generate_credit_simulation_dataset",
    "validate_dataset_dir",
    "write_validation_summary",
    "import_dataset_dir",
    "summarize_imported_dataset",
    "replay_imported_dataset",
    "rerun_imported_dataset",
    "run_full_workflow",
    "handle_request",
    "create_http_server",
    "serve_http_api",
    "ensure_registry_db",
    "register_dataset",
    "list_registered_datasets",
    "get_registered_dataset",
    "list_workflow_runs",
    "get_workflow_run",
    "load_document_bundle",
    "load_question",
    "load_rule",
    "load_trace",
    "resolve_trace_path",
    "summarize_trace",
]
