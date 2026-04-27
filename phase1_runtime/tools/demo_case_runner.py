from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile
from typing import Any

from .demo_case_service import DEMO_CASES_DIR, _load_json, _resolve_case_dir, get_workspace_demo_case
from ..product import solve_workspace_request
from ..prototype import run_prototype_flow


def _expected_subset(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    subset: dict[str, Any] = {}
    for key in (
        "scenario_id",
        "parser_status",
        "route_decision",
        "final_decision",
        "decision_text",
        "composition_pattern",
    ):
        if key in expected:
            if key == "composition_pattern":
                subset[key] = actual.get(key) or ((actual.get("solution_view") or {}).get("route") or {}).get("composition_pattern")
            else:
                subset[key] = actual.get(key)
    if "unsupported_file_count" in expected:
        subset["unsupported_file_count"] = len(actual.get("unsupported_files", []))
    asset_pipeline = expected.get("asset_pipeline")
    if isinstance(asset_pipeline, dict):
        actual_pipeline = actual.get("asset_pipeline", {})
        subset["asset_pipeline"] = {
            field: actual_pipeline.get(field)
            for field in ("auto_status",)
            if field in asset_pipeline
        }
        feedback_payload = ((actual_pipeline.get("feedback") or {}).get("payload") or {})
        promotion_draft = ((actual_pipeline.get("promotion") or {}).get("draft") or {})
        if "recommended_action" in asset_pipeline:
            subset["asset_pipeline"]["recommended_action"] = feedback_payload.get("recommended_action")
        if "patch_type" in asset_pipeline:
            subset["asset_pipeline"]["patch_type"] = ((promotion_draft.get("payload") or {}).get("patch_target") or {}).get("patch_type")
    return subset


def run_demo_case(case_ref: str, *, work_dir: str | Path | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    case_dir = _resolve_case_dir(case_ref)
    payload = _load_json(case_dir / "input.json")
    entry = payload["entry"]

    if entry == "prototype":
        return run_prototype_flow(
            flow_id=str(payload["flow_id"]),
            work_dir=work_dir or tempfile.mkdtemp(prefix="prototype_case_"),
            db_path=db_path or Path(tempfile.mkdtemp(prefix="prototype_db_")) / "registry.db",
        )

    if entry != "workspace":
        raise ValueError(f"unsupported demo case entry: {entry}")

    workspace_case = get_workspace_demo_case(str(case_dir))
    return solve_workspace_request(
        question_text=str(payload["question_text"]),
        materials=workspace_case["materials"],
        scenario_id=payload.get("scenario_id"),
        work_dir=work_dir or tempfile.mkdtemp(prefix="workspace_case_"),
        db_path=db_path or Path(tempfile.mkdtemp(prefix="workspace_db_")) / "registry.db",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a demo case from demo_cases/")
    parser.add_argument("case_ref", help="Case path or case id under demo_cases/")
    parser.add_argument("--check-expected", action="store_true", help="Compare core fields against expected.json")
    args = parser.parse_args()

    case_dir = _resolve_case_dir(args.case_ref)
    result = run_demo_case(args.case_ref)
    if args.check_expected:
        expected = _load_json(case_dir / "expected.json")
        summary = {
            "case": str(case_dir),
            "expected": expected,
            "actual_subset": _expected_subset(result, expected),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
