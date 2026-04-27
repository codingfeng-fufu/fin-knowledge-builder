from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any


FINAL_STATUSES = {
    "completed",
    "failed",
    "insufficient_evidence",
    "need_human_review",
    "cancelled",
    "timed_out",
}


def _load_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise RuntimeError("missing stdin payload")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("stdin payload must be a JSON object")
    return payload


def _request_json(response: Any, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed ({response.status_code}): {response.get_json(silent=True)}")
    payload = response.get_json(silent=True) or {}
    if not payload.get("success", False):
        raise RuntimeError(f"{label} failed: {payload}")
    return payload["data"]


def main() -> None:
    payload = _load_payload()
    backend_root = Path(str(payload["backend_root"])).resolve()
    if not backend_root.exists():
        raise RuntimeError(f"backend_root not found: {backend_root}")

    sys.path.insert(0, str(backend_root))
    from app import create_app  # type: ignore

    app = create_app()
    client = app.test_client()

    rerun_task_id = str(payload.get("rerun_task_id") or "").strip()
    if rerun_task_id:
        task = _request_json(
            client.post(
                f"/api/discovery/tasks/{rerun_task_id}/rerun",
                json={
                    "use_llm": bool(payload.get("use_llm", True)),
                    "discovery_mode": payload.get("discovery_mode", "emergent"),
                    "metadata": payload.get("metadata", {}),
                },
            ),
            "rerun_discovery_task",
        )
        task_id = task["task_id"]
    else:
        rule_set = _request_json(
            client.post(
                "/api/discovery/rule-sets/import",
                json={
                    "name": payload["rule_set_name"],
                    "description": payload.get("rule_set_description", ""),
                    "rules": payload["rules"],
                    "metadata": payload.get("rule_set_metadata", {}),
                },
            ),
            "import_rule_set",
        )
        rule_set_id = rule_set["rule_set_id"]

        document_set_id = None
        documents = payload.get("documents") or []
        if documents:
            document_import = _request_json(
                client.post(
                    "/api/discovery/documents/import",
                    json={
                        "name": payload["document_set_name"],
                        "description": payload.get("document_set_description", ""),
                        "documents": documents,
                        "metadata": payload.get("document_set_metadata", {}),
                        "chunk_size": int(payload.get("chunk_size", 800)),
                        "overlap": int(payload.get("overlap", 120)),
                    },
                ),
                "import_documents",
            )
            document_set_id = (document_import.get("document_set") or {}).get("document_set_id")

        task = _request_json(
            client.post(
                "/api/discovery/tasks/discover-rule",
                json={
                    "query": payload["query"],
                    "context": payload.get("context", ""),
                    "rule_set_id": rule_set_id,
                    "document_set_id": document_set_id,
                    "use_llm": bool(payload.get("use_llm", True)),
                    "discovery_mode": payload.get("discovery_mode", "emergent"),
                    "metadata": payload.get("metadata", {}),
                    "deduplicate": False,
                },
            ),
            "create_discovery_task",
        )
        task_id = task["task_id"]

    timeout_seconds = max(1, int(payload.get("timeout_seconds", 120)))
    poll_interval = max(0.05, float(payload.get("poll_interval_seconds", 0.25)))
    deadline = time.time() + timeout_seconds
    final_task = task
    while time.time() < deadline:
        final_task = _request_json(
            client.get(f"/api/discovery/tasks/{task_id}"),
            "get_task",
        )
        if str(final_task.get("status")) in FINAL_STATUSES:
            break
        time.sleep(poll_interval)
    else:
        raise TimeoutError(f"rule discovery timed out after {timeout_seconds}s")

    result = _request_json(
        client.get(f"/api/discovery/tasks/{task_id}/result"),
        "get_task_result",
    )
    stages = _request_json(
        client.get(f"/api/discovery/tasks/{task_id}/stages"),
        "list_task_stages",
    )
    logs = _request_json(
        client.get(f"/api/discovery/tasks/{task_id}/logs"),
        "get_task_logs",
    )

    print(
        json.dumps(
            {
                "success": True,
                "task": final_task,
                "result": result,
                "stages": stages.get("stages", []),
                "logs": logs.get("logs", []),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
