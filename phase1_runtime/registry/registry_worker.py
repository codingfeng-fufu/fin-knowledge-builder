from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..datasets import run_full_workflow
from .registry_service import complete_registered_workflow_run, get_workflow_run, mark_workflow_run_running


def execute_registered_workflow_run(run_id: str, db_path: str | Path, trace_dir: str | Path) -> dict[str, object]:
    run = get_workflow_run(run_id, db_path=db_path)
    mark_workflow_run_running(run_id, db_path=db_path)
    try:
        result = run_full_workflow(dataset_dir=run["dataset_dir"], trace_dir=trace_dir, db_path=db_path)
        rerun_summary = result.get("rerun_summary", {})
        final_decision = rerun_summary.get("rerun_final_decision") or result.get("import_summary", {}).get("final_decision")
        return complete_registered_workflow_run(
            run_id=run_id,
            result=result,
            error=None,
            rerun_trace_path=rerun_summary.get("rerun_trace_path"),
            final_decision=final_decision,
            db_path=db_path,
        )
    except Exception as exc:
        return complete_registered_workflow_run(
            run_id=run_id,
            result=None,
            error={"message": str(exc)},
            rerun_trace_path=None,
            final_decision=None,
            db_path=db_path,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute a queued workflow run from the registry.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--trace-dir", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    result = execute_registered_workflow_run(args.run_id, args.db_path, args.trace_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
