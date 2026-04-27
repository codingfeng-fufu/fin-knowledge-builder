from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


DEFAULT_DB_PATH = Path("phase1_runtime/state/registry.db")


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def ensure_registry_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_registry (
                dataset_id TEXT PRIMARY KEY,
                scenario_name TEXT NOT NULL,
                dataset_dir TEXT NOT NULL,
                validation_valid INTEGER NOT NULL,
                registered_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                summary_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workflow_run_registry (
                run_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                dataset_dir TEXT NOT NULL,
                request_id TEXT,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                result_json TEXT,
                error_json TEXT,
                rerun_trace_path TEXT,
                final_decision TEXT,
                FOREIGN KEY(dataset_id) REFERENCES dataset_registry(dataset_id)
            )
            """
        )
    return path


@contextmanager
def registry_connection(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    path = ensure_registry_db(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def upsert_dataset_record(
    dataset_id: str,
    scenario_name: str,
    dataset_dir: str,
    validation_valid: bool,
    source: str,
    metadata: dict[str, Any],
    summary: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    now = _timestamp()
    payload = {
        "dataset_id": dataset_id,
        "scenario_name": scenario_name,
        "dataset_dir": dataset_dir,
        "validation_valid": int(validation_valid),
        "registered_at": now,
        "updated_at": now,
        "source": source,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "summary_json": json.dumps(summary, ensure_ascii=False),
    }

    with registry_connection(db_path) as connection:
        existing = connection.execute(
            "SELECT registered_at FROM dataset_registry WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
        if existing is not None:
            payload["registered_at"] = existing["registered_at"]

        connection.execute(
            """
            INSERT INTO dataset_registry (
                dataset_id, scenario_name, dataset_dir, validation_valid,
                registered_at, updated_at, source, metadata_json, summary_json
            ) VALUES (
                :dataset_id, :scenario_name, :dataset_dir, :validation_valid,
                :registered_at, :updated_at, :source, :metadata_json, :summary_json
            )
            ON CONFLICT(dataset_id) DO UPDATE SET
                scenario_name = excluded.scenario_name,
                dataset_dir = excluded.dataset_dir,
                validation_valid = excluded.validation_valid,
                updated_at = excluded.updated_at,
                source = excluded.source,
                metadata_json = excluded.metadata_json,
                summary_json = excluded.summary_json
            """,
            payload,
        )

    return get_dataset_record(dataset_id, db_path=db_path)


def get_dataset_record(dataset_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with registry_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM dataset_registry WHERE dataset_id = ?",
            (dataset_id,),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"dataset_id not found: {dataset_id}")
    return _dataset_row_to_dict(row)


def list_dataset_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with registry_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM dataset_registry ORDER BY registered_at ASC"
        ).fetchall()
    return [_dataset_row_to_dict(row) for row in rows]


def insert_workflow_run(
    run_id: str,
    dataset_id: str,
    dataset_dir: str,
    request_id: str | None,
    action: str,
    status: str,
    started_at: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with registry_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO workflow_run_registry (
                run_id, dataset_id, dataset_dir, request_id, action,
                status, started_at, finished_at, result_json, error_json,
                rerun_trace_path, final_decision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
            """,
            (run_id, dataset_id, dataset_dir, request_id, action, status, started_at),
        )
    return get_workflow_run_record(run_id, db_path=db_path)


def update_workflow_run_status(
    run_id: str,
    status: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with registry_connection(db_path) as connection:
        connection.execute(
            "UPDATE workflow_run_registry SET status = ? WHERE run_id = ?",
            (status, run_id),
        )
    return get_workflow_run_record(run_id, db_path=db_path)


def finalize_workflow_run(
    run_id: str,
    status: str,
    result: dict[str, Any] | None,
    error: dict[str, Any] | None,
    rerun_trace_path: str | None,
    final_decision: str | None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with registry_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE workflow_run_registry
            SET status = ?, finished_at = ?, result_json = ?, error_json = ?,
                rerun_trace_path = ?, final_decision = ?
            WHERE run_id = ?
            """,
            (
                status,
                _timestamp(),
                None if result is None else json.dumps(result, ensure_ascii=False),
                None if error is None else json.dumps(error, ensure_ascii=False),
                rerun_trace_path,
                final_decision,
                run_id,
            ),
        )
    return get_workflow_run_record(run_id, db_path=db_path)


def get_workflow_run_record(run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with registry_connection(db_path) as connection:
        row = connection.execute(
            "SELECT * FROM workflow_run_registry WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if row is None:
        raise FileNotFoundError(f"run_id not found: {run_id}")
    return _workflow_row_to_dict(row)


def list_workflow_run_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with registry_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM workflow_run_registry ORDER BY started_at DESC"
        ).fetchall()
    return [_workflow_row_to_dict(row) for row in rows]


def _dataset_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "dataset_id": row["dataset_id"],
        "scenario_name": row["scenario_name"],
        "dataset_dir": row["dataset_dir"],
        "validation_valid": bool(row["validation_valid"]),
        "registered_at": row["registered_at"],
        "updated_at": row["updated_at"],
        "source": row["source"],
        "metadata": json.loads(row["metadata_json"]),
        "summary": json.loads(row["summary_json"]),
    }


def _workflow_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "dataset_id": row["dataset_id"],
        "dataset_dir": row["dataset_dir"],
        "request_id": row["request_id"],
        "action": row["action"],
        "status": row["status"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "result": None if row["result_json"] is None else json.loads(row["result_json"]),
        "error": None if row["error_json"] is None else json.loads(row["error_json"]),
        "rerun_trace_path": row["rerun_trace_path"],
        "final_decision": row["final_decision"],
    }
