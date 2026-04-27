from __future__ import annotations

from base64 import b64encode
import json
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {"txt", "md", "json", "csv", "log", "html", "htm"}
DEMO_CASES_DIR = Path("demo_cases")
CATALOG_PATH = DEMO_CASES_DIR / "catalog.json"
DEFAULT_WORKSPACE_CASE_REF = "workspace/fund_docx_direct_warn"
FEATURED_WORKSPACE_CASE_REF = "workspace/equity_research_h3_code_upside_calc"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_case_dir(case_ref: str) -> Path:
    raw = Path(case_ref)
    if raw.exists():
        return raw
    candidate = DEMO_CASES_DIR / case_ref
    if candidate.exists():
        return candidate
    candidate = DEMO_CASES_DIR / "workspace" / case_ref
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"demo case not found: {case_ref}")


def _material_payload(case_dir: Path, item: dict[str, Any]) -> dict[str, Any]:
    relative_path = Path(str(item["path"]))
    material_path = case_dir / relative_path
    name = str(item.get("name") or material_path.name)
    hidden_in_ui = bool(item.get("hidden_in_ui"))
    suffix = material_path.suffix.lower().lstrip(".")
    if suffix in TEXT_EXTENSIONS:
        return {
            "name": name,
            "content": material_path.read_text(encoding="utf-8"),
            "size": material_path.stat().st_size,
            "demo_source": "workspace_sample",
            "hidden_in_ui": hidden_in_ui,
        }
    return {
        "name": name,
        "content_base64": b64encode(material_path.read_bytes()).decode("ascii"),
        "size": material_path.stat().st_size,
        "demo_source": "workspace_sample",
        "hidden_in_ui": hidden_in_ui,
    }


def _case_note(case_dir: Path) -> str:
    notes_path = case_dir / "notes.md"
    if not notes_path.exists():
        return ""
    lines = [line.strip() for line in notes_path.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        if not line or line.startswith("#"):
            continue
        return line
    return ""


def list_workspace_demo_cases() -> dict[str, Any]:
    catalog = _load_json(CATALOG_PATH)
    items = []
    for item in catalog.get("cases", []):
        if item.get("entry") != "workspace":
            continue
        case_dir = DEMO_CASES_DIR / str(item["path"])
        input_payload = _load_json(case_dir / "input.json")
        expected_payload = _load_json(case_dir / "expected.json")
        items.append(
            {
                "case_ref": str(item["path"]),
                "case_id": item["case_id"],
                "title": item["title"],
                "featured": str(item["path"]) == FEATURED_WORKSPACE_CASE_REF,
                "featured_label": "重点样本" if str(item["path"]) == FEATURED_WORKSPACE_CASE_REF else "",
                "scenario_id": input_payload.get("scenario_id") or expected_payload.get("scenario_id"),
                "question_text": input_payload.get("question_text", ""),
                "material_count": len(input_payload.get("materials", [])),
                "related_question_count": len(input_payload.get("related_questions", [])),
                "route_decision": expected_payload.get("route_decision"),
                "decision_text": expected_payload.get("decision_text"),
                "note": _case_note(case_dir),
            }
        )
    items.sort(
        key=lambda entry: (
            0 if entry["case_ref"] == FEATURED_WORKSPACE_CASE_REF else 1,
            0 if entry["case_ref"] == DEFAULT_WORKSPACE_CASE_REF else 1,
        )
    )
    return {
        "case_count": len(items),
        "default_case_ref": DEFAULT_WORKSPACE_CASE_REF,
        "cases": items,
    }


def get_workspace_demo_case(case_ref: str) -> dict[str, Any]:
    case_dir = _resolve_case_dir(case_ref)
    input_payload = _load_json(case_dir / "input.json")
    expected_payload = _load_json(case_dir / "expected.json")
    normalized_case_ref = str(case_dir.relative_to(DEMO_CASES_DIR))
    if input_payload.get("entry") != "workspace":
        raise ValueError(f"demo case is not a workspace case: {case_ref}")
    materials = [_material_payload(case_dir, item) for item in input_payload.get("materials", [])]
    return {
        "case_ref": normalized_case_ref,
        "case_name": case_dir.name,
        "featured": normalized_case_ref == FEATURED_WORKSPACE_CASE_REF,
        "scenario_id": input_payload.get("scenario_id") or expected_payload.get("scenario_id"),
        "question_text": input_payload.get("question_text", ""),
        "related_questions": list(input_payload.get("related_questions", [])),
        "materials": materials,
        "expected": expected_payload,
        "note": _case_note(case_dir),
    }
