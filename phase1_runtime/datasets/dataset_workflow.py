from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from ..contracts import validate_dataset_dir
from ..registry.registry_store import DEFAULT_DB_PATH
from .dataset_consume import (
    replay_imported_dataset,
    rerun_imported_dataset,
    summarize_imported_dataset,
)
from .dataset_import import import_dataset_dir


DEFAULT_DATASET_DIR = Path("phase1_runtime/sim_data/demo_set_001")
DEFAULT_RERUN_TRACE_DIR = Path("phase1_runtime/consumption_traces")


def run_full_workflow(
    dataset_dir: str | Path = DEFAULT_DATASET_DIR,
    trace_dir: str | Path = DEFAULT_RERUN_TRACE_DIR,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    validation_summary = validate_dataset_dir(dataset_dir)
    imported = import_dataset_dir(dataset_dir)
    import_summary = summarize_imported_dataset(imported)
    replay_summary = replay_imported_dataset(imported)
    rerun_summary = rerun_imported_dataset(imported, trace_dir=trace_dir, db_path=db_path)

    return {
        "dataset_dir": str(Path(dataset_dir).resolve()),
        "workflow_status": "completed",
        "validation": validation_summary,
        "import_summary": import_summary,
        "replay_summary": replay_summary,
        "rerun_summary": rerun_summary,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the single-case Phase 1 workflow end-to-end.")
    subparsers = parser.add_subparsers(dest="command")

    full_parser = subparsers.add_parser("full", help="Validate, import, replay, and rerun in one command.")
    full_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to consume.")
    full_parser.add_argument("--trace-dir", default=str(DEFAULT_RERUN_TRACE_DIR), help="Directory for rerun traces.")
    full_parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Factory/registry database for published rules.")

    summary_parser = subparsers.add_parser("summary", help="Alias for the import summary stage.")
    summary_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to consume.")

    replay_parser = subparsers.add_parser("replay", help="Alias for the replay stage.")
    replay_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to consume.")

    rerun_parser = subparsers.add_parser("rerun", help="Alias for the rerun comparison stage.")
    rerun_parser.add_argument("--dataset-dir", default=str(DEFAULT_DATASET_DIR), help="Dataset directory to consume.")
    rerun_parser.add_argument("--trace-dir", default=str(DEFAULT_RERUN_TRACE_DIR), help="Directory for rerun traces.")
    rerun_parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="Factory/registry database for published rules.")

    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    incoming = list(sys.argv[1:] if argv is None else argv)
    if not incoming or incoming[0] not in {"full", "summary", "replay", "rerun"}:
        incoming = ["full", *incoming]
    return parser.parse_args(incoming)


def main() -> None:
    args = parse_args()
    if args.command == "full":
        payload = run_full_workflow(dataset_dir=args.dataset_dir, trace_dir=args.trace_dir, db_path=args.db_path)
    else:
        imported = import_dataset_dir(args.dataset_dir)
        if args.command == "summary":
            payload = summarize_imported_dataset(imported)
        elif args.command == "replay":
            payload = replay_imported_dataset(imported)
        elif args.command == "rerun":
            payload = rerun_imported_dataset(imported, trace_dir=args.trace_dir, db_path=args.db_path)
        else:
            raise ValueError(f"unsupported command {args.command}")

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
