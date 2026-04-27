from __future__ import annotations

from typing import Any

from ..schema import ValidatorRef


class ValidationError(ValueError):
    """Raised when an error-severity validator fails."""


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_value(value: Any, schema: dict[str, Any], path: str) -> list[str]:
    errors: list[str] = []
    schema_type = schema.get("type")

    if schema_type == "object":
        if not isinstance(value, dict):
            return [f"{path} must be an object"]
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key} is required")
        for key, child_schema in properties.items():
            if key in value:
                errors.extend(_validate_value(value[key], child_schema, f"{path}.{key}"))
        return errors

    if schema_type == "array":
        if not isinstance(value, list):
            return [f"{path} must be an array"]
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                errors.extend(_validate_value(item, item_schema, f"{path}[{index}]"))
        return errors

    if schema_type == "string" and not isinstance(value, str):
        errors.append(f"{path} must be a string")
    elif schema_type == "number" and not _is_number(value):
        errors.append(f"{path} must be a number")
    elif schema_type == "boolean" and not isinstance(value, bool):
        errors.append(f"{path} must be a boolean")
    return errors


def run_validator(validator: ValidatorRef, payload: dict[str, Any], schema: dict[str, Any] | None = None) -> dict[str, Any]:
    ok = True
    details: list[str] = []

    if validator.validator_id == "schema.validate":
        if schema is None:
            ok = False
            details.append("schema.validate requires a schema")
        else:
            details = _validate_value(payload, schema, "payload")
            ok = not details
    elif validator.validator_id == "evidence.required":
        evidence_refs = payload.get("evidence_refs")
        ok = isinstance(evidence_refs, list) and len(evidence_refs) > 0
        if not ok:
            details.append("evidence_refs must be a non-empty list")
    elif validator.validator_id == "must_include":
        fields = validator.params.get("fields", [])
        missing = [field for field in fields if field not in payload]
        ok = not missing
        if missing:
            details.append(f"missing required fields: {', '.join(missing)}")
    else:
        ok = False
        details.append(f"unknown validator {validator.validator_id}")

    result = {
        "validator_id": validator.validator_id,
        "target": validator.target,
        "severity": validator.severity,
        "ok": ok,
        "details": details,
    }

    if not ok and validator.severity == "error":
        raise ValidationError("; ".join(details) or f"{validator.validator_id} failed")

    return result
