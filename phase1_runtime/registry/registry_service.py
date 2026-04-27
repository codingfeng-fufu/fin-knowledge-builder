from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any
from uuid import uuid4

from ..datasets import DEFAULT_RERUN_TRACE_DIR, import_dataset_dir, run_full_workflow
from .registry_store import (
    DEFAULT_DB_PATH,
    ensure_registry_db,
    finalize_workflow_run,
    get_dataset_record,
    get_workflow_run_record,
    insert_workflow_run,
    list_dataset_records,
    list_workflow_run_records,
    update_workflow_run_status,
    upsert_dataset_record,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKER_PROCESSES = []


def _track_worker_process(process):
    active = []
    for item in ACTIVE_WORKER_PROCESSES:
        if item.poll() is None:
            active.append(item)
    active.append(process)
    ACTIVE_WORKER_PROCESSES[:] = active



def register_dataset(
    dataset_dir: str | Path,
    source: str = "manual",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    imported = import_dataset_dir(dataset_dir)
    summary = imported.to_summary()
    summary["final_decision"] = (imported.execution_trace.final_result or {}).get("decision")
    return upsert_dataset_record(
        dataset_id=imported.simulation_dataset.dataset_id,
        scenario_name=imported.simulation_dataset.scenario_name,
        dataset_dir=str(imported.dataset_dir),
        validation_valid=bool(imported.validation_summary.get("valid", False)),
        source=source,
        metadata={} if metadata is None else metadata,
        summary=summary,
        db_path=db_path,
    )


def list_registered_datasets(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_registry_db(db_path)
    items = list_dataset_records(db_path=db_path)
    return {
        "db_path": str(Path(db_path).resolve()),
        "dataset_count": len(items),
        "datasets": items,
    }


def get_registered_dataset(dataset_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_registry_db(db_path)
    return get_dataset_record(dataset_id, db_path=db_path)


def run_registered_workflow_sync(
    dataset_id: str,
    request_id: str | None = None,
    trace_dir: str | Path = DEFAULT_RERUN_TRACE_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_registry_db(db_path)
    dataset = get_dataset_record(dataset_id, db_path=db_path)
    run_id = f"run_{uuid4().hex[:12]}"
    insert_workflow_run(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_dir=str(dataset["dataset_dir"]),
        request_id=request_id,
        action="workflow.full",
        status="running",
        started_at=str(__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()),
        db_path=db_path,
    )

    try:
        result = run_full_workflow(dataset_dir=dataset["dataset_dir"], trace_dir=trace_dir, db_path=db_path)
        rerun_summary = result.get("rerun_summary", {})
        final_decision = rerun_summary.get("rerun_final_decision") or result.get("import_summary", {}).get("final_decision")
        record = finalize_workflow_run(
            run_id=run_id,
            status="completed",
            result=result,
            error=None,
            rerun_trace_path=rerun_summary.get("rerun_trace_path"),
            final_decision=final_decision,
            db_path=db_path,
        )
    except Exception as exc:
        record = finalize_workflow_run(
            run_id=run_id,
            status="failed",
            result=None,
            error={"message": str(exc)},
            rerun_trace_path=None,
            final_decision=None,
            db_path=db_path,
        )
        raise

    return record


def submit_registered_workflow(
    dataset_id: str,
    request_id: str | None = None,
    trace_dir: str | Path = DEFAULT_RERUN_TRACE_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    ensure_registry_db(db_path)
    dataset = get_dataset_record(dataset_id, db_path=db_path)
    run_id = f"run_{uuid4().hex[:12]}"
    queued = insert_workflow_run(
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_dir=str(dataset["dataset_dir"]),
        request_id=request_id,
        action="workflow.full",
        status="queued",
        started_at=str(__import__('datetime').datetime.now(__import__('datetime').UTC).isoformat()),
        db_path=db_path,
    )

    command = [
        sys.executable,
        "-m",
        "phase1_runtime.registry.registry_worker",
        "--run-id",
        run_id,
        "--db-path",
        str(db_path),
        "--trace-dir",
        str(trace_dir),
    ]
    process = subprocess.Popen(
        command,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _track_worker_process(process)
    return queued


def mark_workflow_run_running(run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_registry_db(db_path)
    return update_workflow_run_status(run_id=run_id, status="running", db_path=db_path)


def complete_registered_workflow_run(
    run_id: str,
    result: dict[str, Any] | None,
    error: dict[str, Any] | None,
    rerun_trace_path: str | None,
    final_decision: str | None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    status = "completed" if error is None else "failed"
    return finalize_workflow_run(
        run_id=run_id,
        status=status,
        result=result,
        error=error,
        rerun_trace_path=rerun_trace_path,
        final_decision=final_decision,
        db_path=db_path,
    )


def list_workflow_runs(db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_registry_db(db_path)
    items = list_workflow_run_records(db_path=db_path)
    return {
        "db_path": str(Path(db_path).resolve()),
        "run_count": len(items),
        "runs": items,
    }


def get_workflow_run(run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    ensure_registry_db(db_path)
    return get_workflow_run_record(run_id, db_path=db_path)
