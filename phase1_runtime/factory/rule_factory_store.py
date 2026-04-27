from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from ..registry.registry_store import DEFAULT_DB_PATH, ensure_registry_db


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def ensure_rule_factory_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    path = ensure_registry_db(db_path)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS case_store (
                case_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                scenario_name TEXT NOT NULL,
                dataset_dir TEXT NOT NULL,
                title TEXT NOT NULL,
                question_text TEXT NOT NULL,
                review_status TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS candidate_rule_draft_store (
                draft_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                proposed_rule_id TEXT NOT NULL,
                source_rule_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS review_task_store (
                review_task_id TEXT PRIMARY KEY,
                draft_id TEXT NOT NULL,
                status TEXT NOT NULL,
                assignee TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                result_note TEXT,
                checklist_json TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS published_rule_version_store (
                rule_version_id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                version_label TEXT NOT NULL,
                source_draft_id TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS case_rule_link_store (
                link_id TEXT PRIMARY KEY,
                case_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_version_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rollback_store (
                rollback_id TEXT PRIMARY KEY,
                rule_version_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_store (
                feedback_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                case_id TEXT,
                route_decision TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                rule_ids_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_run_store (
                workspace_run_id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                case_id TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                question_text TEXT NOT NULL,
                route_decision TEXT NOT NULL,
                final_decision TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        review_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(review_task_store)").fetchall()
        }
        if "payload_json" not in review_columns:
            connection.execute(
                "ALTER TABLE review_task_store ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"
            )
    return path


@contextmanager
def rule_factory_connection(db_path: str | Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    path = ensure_rule_factory_db(db_path)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def upsert_case_record(
    case_id: str,
    dataset_id: str,
    scenario_name: str,
    dataset_dir: str,
    title: str,
    question_text: str,
    review_status: str,
    source: str,
    payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    now = _timestamp()
    record = {
        'case_id': case_id,
        'dataset_id': dataset_id,
        'scenario_name': scenario_name,
        'dataset_dir': dataset_dir,
        'title': title,
        'question_text': question_text,
        'review_status': review_status,
        'source': source,
        'created_at': now,
        'updated_at': now,
        'payload_json': json.dumps(payload, ensure_ascii=False),
    }
    with rule_factory_connection(db_path) as connection:
        existing = connection.execute('SELECT created_at FROM case_store WHERE case_id = ?', (case_id,)).fetchone()
        if existing is not None:
            record['created_at'] = existing['created_at']
        connection.execute(
            """
            INSERT INTO case_store (
                case_id, dataset_id, scenario_name, dataset_dir, title,
                question_text, review_status, source, created_at, updated_at, payload_json
            ) VALUES (
                :case_id, :dataset_id, :scenario_name, :dataset_dir, :title,
                :question_text, :review_status, :source, :created_at, :updated_at, :payload_json
            )
            ON CONFLICT(case_id) DO UPDATE SET
                dataset_id = excluded.dataset_id,
                scenario_name = excluded.scenario_name,
                dataset_dir = excluded.dataset_dir,
                title = excluded.title,
                question_text = excluded.question_text,
                review_status = excluded.review_status,
                source = excluded.source,
                updated_at = excluded.updated_at,
                payload_json = excluded.payload_json
            """,
            record,
        )
    return get_case_record(case_id, db_path=db_path)


def insert_candidate_rule_draft(
    draft_id: str,
    case_id: str,
    proposed_rule_id: str,
    source_rule_id: str | None,
    status: str,
    payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    now = _timestamp()
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO candidate_rule_draft_store (
                draft_id, case_id, proposed_rule_id, source_rule_id,
                status, created_at, updated_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (draft_id, case_id, proposed_rule_id, source_rule_id, status, now, now, json.dumps(payload, ensure_ascii=False)),
        )
    return get_candidate_rule_draft(draft_id, db_path=db_path)


def update_candidate_rule_draft_status(
    draft_id: str,
    status: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            'UPDATE candidate_rule_draft_store SET status = ?, updated_at = ? WHERE draft_id = ?',
            (status, _timestamp(), draft_id),
        )
    return get_candidate_rule_draft(draft_id, db_path=db_path)


def insert_review_task(
    review_task_id: str,
    draft_id: str,
    status: str,
    assignee: str,
    checklist: list[dict[str, Any]],
    result_note: str | None,
    payload: dict[str, Any] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    now = _timestamp()
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO review_task_store (
                review_task_id, draft_id, status, assignee,
                created_at, updated_at, result_note, checklist_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_task_id,
                draft_id,
                status,
                assignee,
                now,
                now,
                result_note,
                json.dumps(checklist, ensure_ascii=False),
                json.dumps({} if payload is None else payload, ensure_ascii=False),
            ),
        )
    return get_review_task(review_task_id, db_path=db_path)


def update_review_task(
    review_task_id: str,
    status: str,
    result_note: str | None,
    checklist: list[dict[str, Any]] | None,
    payload: dict[str, Any] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT checklist_json, payload_json FROM review_task_store WHERE review_task_id = ?', (review_task_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f'review_task_id not found: {review_task_id}')
        checklist_json = row['checklist_json'] if checklist is None else json.dumps(checklist, ensure_ascii=False)
        payload_json = row['payload_json'] if payload is None else json.dumps(payload, ensure_ascii=False)
        connection.execute(
            'UPDATE review_task_store SET status = ?, updated_at = ?, result_note = ?, checklist_json = ?, payload_json = ? WHERE review_task_id = ?',
            (status, _timestamp(), result_note, checklist_json, payload_json, review_task_id),
        )
    return get_review_task(review_task_id, db_path=db_path)


def insert_rule_version(
    rule_version_id: str,
    rule_id: str,
    version_label: str,
    source_draft_id: str,
    status: str,
    payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO published_rule_version_store (
                rule_version_id, rule_id, version_label, source_draft_id,
                status, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (rule_version_id, rule_id, version_label, source_draft_id, status, _timestamp(), json.dumps(payload, ensure_ascii=False)),
        )
    return get_rule_version(rule_version_id, db_path=db_path)


def update_rule_version_status(
    rule_version_id: str,
    status: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            'UPDATE published_rule_version_store SET status = ? WHERE rule_version_id = ?',
            (status, rule_version_id),
        )
    return get_rule_version(rule_version_id, db_path=db_path)


def insert_case_rule_link(
    link_id: str,
    case_id: str,
    rule_id: str,
    rule_version_id: str,
    relation_type: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO case_rule_link_store (
                link_id, case_id, rule_id, rule_version_id, relation_type, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (link_id, case_id, rule_id, rule_version_id, relation_type, _timestamp()),
        )
    return get_case_rule_link(link_id, db_path=db_path)


def insert_rollback_record(
    rollback_id: str,
    rule_version_id: str,
    rule_id: str,
    reason: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            'INSERT INTO rollback_store (rollback_id, rule_version_id, rule_id, reason, created_at) VALUES (?, ?, ?, ?, ?)',
            (rollback_id, rule_version_id, rule_id, reason, _timestamp()),
        )
    return get_rollback_record(rollback_id, db_path=db_path)


def insert_feedback_record(
    feedback_id: str,
    trace_id: str,
    case_id: str | None,
    route_decision: str,
    feedback_type: str,
    rule_ids: list[str],
    payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO feedback_store (
                feedback_id, trace_id, case_id, route_decision, feedback_type,
                rule_ids_json, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                trace_id,
                case_id,
                route_decision,
                feedback_type,
                json.dumps(rule_ids, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
                _timestamp(),
            ),
        )
    return get_feedback_record(feedback_id, db_path=db_path)


def insert_workspace_run_record(
    workspace_run_id: str,
    trace_id: str,
    case_id: str,
    scenario_id: str,
    question_text: str,
    route_decision: str,
    final_decision: str,
    status: str,
    payload: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO workspace_run_store (
                workspace_run_id, trace_id, case_id, scenario_id, question_text,
                route_decision, final_decision, status, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_run_id,
                trace_id,
                case_id,
                scenario_id,
                question_text,
                route_decision,
                final_decision,
                status,
                _timestamp(),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
    return get_workspace_run_record(workspace_run_id, db_path=db_path)


def get_case_record(case_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM case_store WHERE case_id = ?', (case_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'case_id not found: {case_id}')
    return _case_row_to_dict(row)


def list_case_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM case_store ORDER BY created_at ASC').fetchall()
    return [_case_row_to_dict(row) for row in rows]


def get_candidate_rule_draft(draft_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM candidate_rule_draft_store WHERE draft_id = ?', (draft_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'draft_id not found: {draft_id}')
    return _draft_row_to_dict(row)


def list_candidate_rule_drafts(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM candidate_rule_draft_store ORDER BY created_at ASC').fetchall()
    return [_draft_row_to_dict(row) for row in rows]


def get_review_task(review_task_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM review_task_store WHERE review_task_id = ?', (review_task_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'review_task_id not found: {review_task_id}')
    return _review_task_row_to_dict(row)


def list_review_tasks(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM review_task_store ORDER BY created_at ASC').fetchall()
    return [_review_task_row_to_dict(row) for row in rows]


def get_rule_version(rule_version_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM published_rule_version_store WHERE rule_version_id = ?', (rule_version_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'rule_version_id not found: {rule_version_id}')
    return _rule_version_row_to_dict(row)


def list_rule_versions(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM published_rule_version_store ORDER BY created_at ASC').fetchall()
    return [_rule_version_row_to_dict(row) for row in rows]


def count_rule_versions(rule_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> int:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT COUNT(*) AS count FROM published_rule_version_store WHERE rule_id = ?', (rule_id,)).fetchone()
    return int(row['count'])


def get_case_rule_link(link_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM case_rule_link_store WHERE link_id = ?', (link_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'link_id not found: {link_id}')
    return _case_rule_link_row_to_dict(row)


def list_case_rule_links(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM case_rule_link_store ORDER BY created_at ASC').fetchall()
    return [_case_rule_link_row_to_dict(row) for row in rows]


def get_rollback_record(rollback_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM rollback_store WHERE rollback_id = ?', (rollback_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'rollback_id not found: {rollback_id}')
    return _rollback_row_to_dict(row)


def list_rollback_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM rollback_store ORDER BY created_at ASC').fetchall()
    return [_rollback_row_to_dict(row) for row in rows]


def get_feedback_record(feedback_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM feedback_store WHERE feedback_id = ?', (feedback_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'feedback_id not found: {feedback_id}')
    return _feedback_row_to_dict(row)


def list_feedback_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM feedback_store ORDER BY created_at ASC').fetchall()
    return [_feedback_row_to_dict(row) for row in rows]


def get_workspace_run_record(workspace_run_id: str, db_path: str | Path = DEFAULT_DB_PATH) -> dict[str, Any]:
    with rule_factory_connection(db_path) as connection:
        row = connection.execute('SELECT * FROM workspace_run_store WHERE workspace_run_id = ?', (workspace_run_id,)).fetchone()
    if row is None:
        raise FileNotFoundError(f'workspace_run_id not found: {workspace_run_id}')
    return _workspace_run_row_to_dict(row)


def list_workspace_run_records(db_path: str | Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    with rule_factory_connection(db_path) as connection:
        rows = connection.execute('SELECT * FROM workspace_run_store ORDER BY created_at ASC').fetchall()
    return [_workspace_run_row_to_dict(row) for row in rows]


def _case_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'case_id': row['case_id'],
        'dataset_id': row['dataset_id'],
        'scenario_name': row['scenario_name'],
        'dataset_dir': row['dataset_dir'],
        'title': row['title'],
        'question_text': row['question_text'],
        'review_status': row['review_status'],
        'source': row['source'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'payload': json.loads(row['payload_json']),
    }


def _draft_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'draft_id': row['draft_id'],
        'case_id': row['case_id'],
        'proposed_rule_id': row['proposed_rule_id'],
        'source_rule_id': row['source_rule_id'],
        'status': row['status'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'payload': json.loads(row['payload_json']),
    }


def _review_task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'review_task_id': row['review_task_id'],
        'draft_id': row['draft_id'],
        'status': row['status'],
        'assignee': row['assignee'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
        'result_note': row['result_note'],
        'checklist': json.loads(row['checklist_json']),
        'payload': json.loads(row['payload_json']),
    }


def _rule_version_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'rule_version_id': row['rule_version_id'],
        'rule_id': row['rule_id'],
        'version_label': row['version_label'],
        'source_draft_id': row['source_draft_id'],
        'status': row['status'],
        'created_at': row['created_at'],
        'payload': json.loads(row['payload_json']),
    }


def _case_rule_link_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'link_id': row['link_id'],
        'case_id': row['case_id'],
        'rule_id': row['rule_id'],
        'rule_version_id': row['rule_version_id'],
        'relation_type': row['relation_type'],
        'created_at': row['created_at'],
    }


def _rollback_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'rollback_id': row['rollback_id'],
        'rule_version_id': row['rule_version_id'],
        'rule_id': row['rule_id'],
        'reason': row['reason'],
        'created_at': row['created_at'],
    }


def _feedback_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'feedback_id': row['feedback_id'],
        'trace_id': row['trace_id'],
        'case_id': row['case_id'],
        'route_decision': row['route_decision'],
        'feedback_type': row['feedback_type'],
        'rule_ids': json.loads(row['rule_ids_json']),
        'payload': json.loads(row['payload_json']),
        'created_at': row['created_at'],
    }


def _workspace_run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        'workspace_run_id': row['workspace_run_id'],
        'trace_id': row['trace_id'],
        'case_id': row['case_id'],
        'scenario_id': row['scenario_id'],
        'question_text': row['question_text'],
        'route_decision': row['route_decision'],
        'final_decision': row['final_decision'],
        'status': row['status'],
        'created_at': row['created_at'],
        'payload': json.loads(row['payload_json']),
    }
