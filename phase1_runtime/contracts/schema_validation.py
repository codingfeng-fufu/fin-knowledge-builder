from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .formal_schemas import build_schema_registry


CORE_DATASET_SCHEMA_BINDINGS: dict[str, str] = {
    "question_struct.json": "question_struct",
    "document_bundle.json": "document_bundle_record",
    "case_record.json": "case_record",
    "rule_pool.json": "rule_pool",
    "review_task.json": "review_task",
    "execution_trace.json": "execution_trace_record",
    "simulation_dataset.json": "simulation_dataset",
    "dataset_manifest.json": "dataset_manifest",
}


@dataclass(slots=True)
class ValidationIssue:
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


class LocalSchemaValidator:
    def __init__(self, registry: dict[str, dict[str, Any]] | None = None) -> None:
        self.registry = build_schema_registry() if registry is None else registry

    def validate_payload(self, payload: Any, schema_name: str) -> list[ValidationIssue]:
        schema = self._schema_for_name(schema_name)
        issues: list[ValidationIssue] = []
        self._validate(payload, schema, "$", issues)
        return issues

    def _schema_for_name(self, schema_name: str) -> dict[str, Any]:
        if schema_name == "rule_pool":
            return {
                "type": "array",
                "items": {"$ref": "rule.schema.json"},
            }
        if schema_name not in self.registry:
            raise KeyError(f"unknown schema name {schema_name}")
        return self.registry[schema_name]

    def _resolve_ref(self, ref: str) -> dict[str, Any]:
        if ref.endswith(".schema.json"):
            target_name = ref.removesuffix(".schema.json")
        else:
            target_name = ref
        if target_name not in self.registry:
            raise KeyError(f"unknown schema ref {ref}")
        return self.registry[target_name]

    def _validate(self, payload: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
        if "$ref" in schema:
            self._validate(payload, self._resolve_ref(schema["$ref"]), path, issues)
            return

        enum_values = schema.get("enum")
        if enum_values is not None and payload not in enum_values:
            issues.append(ValidationIssue(path, f"value {payload!r} not in enum {enum_values!r}"))
            return

        if "type" in schema:
            allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            matched_type = next((item for item in allowed if self._matches_type(payload, item)), None)
            if matched_type is None:
                issues.append(ValidationIssue(path, f"expected type {allowed!r}, got {type(payload).__name__}"))
                return
        else:
            matched_type = None

        if matched_type == "object" or (matched_type is None and isinstance(payload, dict)):
            self._validate_object(payload, schema, path, issues)
        elif matched_type == "array" or (matched_type is None and isinstance(payload, list)):
            self._validate_array(payload, schema, path, issues)

    def _validate_object(self, payload: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
        if not isinstance(payload, dict):
            issues.append(ValidationIssue(path, f"expected object, got {type(payload).__name__}"))
            return

        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in payload:
                issues.append(ValidationIssue(f"{path}.{key}", "missing required field"))

        for key, value in payload.items():
            if key in properties:
                self._validate(value, properties[key], f"{path}.{key}", issues)
                continue

            additional = schema.get("additionalProperties", True)
            if additional is False:
                issues.append(ValidationIssue(f"{path}.{key}", "unexpected property"))
            elif isinstance(additional, dict):
                self._validate(value, additional, f"{path}.{key}", issues)

    def _validate_array(self, payload: Any, schema: dict[str, Any], path: str, issues: list[ValidationIssue]) -> None:
        if not isinstance(payload, list):
            issues.append(ValidationIssue(path, f"expected array, got {type(payload).__name__}"))
            return
        item_schema = schema.get("items")
        if item_schema is None:
            return
        for index, item in enumerate(payload):
            self._validate(item, item_schema, f"{path}[{index}]", issues)

    def _matches_type(self, payload: Any, expected_type: str) -> bool:
        if expected_type == "object":
            return isinstance(payload, dict)
        if expected_type == "array":
            return isinstance(payload, list)
        if expected_type == "string":
            return isinstance(payload, str)
        if expected_type == "boolean":
            return isinstance(payload, bool)
        if expected_type == "number":
            return isinstance(payload, (int, float)) and not isinstance(payload, bool)
        if expected_type == "integer":
            return isinstance(payload, int) and not isinstance(payload, bool)
        if expected_type == "null":
            return payload is None
        return True


def validate_dataset_dir(dataset_dir: str | Path) -> dict[str, Any]:
    root = Path(dataset_dir)
    validator = LocalSchemaValidator()
    file_results: dict[str, Any] = {}
    total_issues = 0

    for filename, schema_name in CORE_DATASET_SCHEMA_BINDINGS.items():
        path = root / filename
        if not path.exists():
            issues = [ValidationIssue(filename, "file not found")]
        else:
            payload = json.loads(path.read_text(encoding="utf-8"))
            issues = validator.validate_payload(payload, schema_name)

        file_results[filename] = {
            "schema": schema_name,
            "valid": len(issues) == 0,
            "issue_count": len(issues),
            "issues": [item.to_dict() for item in issues],
        }
        total_issues += len(issues)

    summary = {
        "dataset_dir": str(root.resolve()),
        "validated_files": len(CORE_DATASET_SCHEMA_BINDINGS),
        "total_issues": total_issues,
        "valid": total_issues == 0,
        "files": file_results,
    }
    return summary


def write_validation_summary(dataset_dir: str | Path) -> dict[str, Any]:
    root = Path(dataset_dir)
    summary = validate_dataset_dir(root)
    output_path = root / "validation_summary.json"
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["summary_file"] = str(output_path)
    return summary


if __name__ == "__main__":
    result = write_validation_summary("phase1_runtime/sim_data/demo_set_001")
    print(json.dumps(result, ensure_ascii=False, indent=2))
