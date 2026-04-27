from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA_DIR = Path("phase1_runtime/json_schemas")
SCHEMA_URI = "https://json-schema.org/draft/2020-12/schema"


def _schema_id(name: str) -> str:
    return f"{name}.schema.json"


def _array(item_schema: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": item_schema}


def build_schema_registry() -> dict[str, dict[str, Any]]:
    input_field = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("input_field"),
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "type": {"type": "string", "enum": ["string", "number", "boolean", "date", "object", "array"]},
            "description": {"type": "string"},
            "hints": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["key", "type", "description"],
        "additionalProperties": False,
    }

    output_field = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("output_field"),
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "type": {"type": "string", "enum": ["string", "number", "boolean", "date", "object", "array"]},
            "description": {"type": "string"},
        },
        "required": ["key", "type", "description"],
        "additionalProperties": False,
    }

    evidence_ref = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("evidence_ref"),
        "type": "object",
        "properties": {
            "doc_id": {"type": "string"},
            "locator": {"type": "object", "additionalProperties": True},
            "snippet_id": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["doc_id", "locator", "snippet_id", "text"],
        "additionalProperties": False,
    }

    validator_ref = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("validator_ref"),
        "type": "object",
        "properties": {
            "validator_id": {"type": "string"},
            "target": {"type": "string"},
            "severity": {"type": "string", "enum": ["error", "warn"]},
            "params": {"type": "object", "additionalProperties": True},
        },
        "required": ["validator_id", "target", "severity"],
        "additionalProperties": False,
    }

    question_struct = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("question_struct"),
        "type": "object",
        "properties": {
            "question_text": {"type": "string"},
            "question_types": _array({"type": "string"}),
            "intents": _array({"type": "string"}),
            "document_types": _array({"type": "string"}),
            "extracted_inputs": {"type": "object", "additionalProperties": True},
        },
        "required": ["question_text", "question_types", "intents", "document_types"],
        "additionalProperties": False,
    }

    rule = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("rule"),
        "type": "object",
        "properties": {
            "rule_id": {"type": "string"},
            "name": {"type": "string"},
            "status": {"type": "string", "enum": ["draft", "candidate", "published", "deprecated"]},
            "version": {"type": "string"},
            "rule_kind": {"type": "string", "enum": ["atomic", "composite"]},
            "rule_family": {"type": "string"},
            "composition": {
                "type": ["object", "null"],
                "properties": {
                    "pattern": {"type": "string"},
                    "source_rule_ids": _array({"type": "string"}),
                    "binding_schema": {"type": "object", "additionalProperties": True},
                },
                "required": ["pattern", "source_rule_ids", "binding_schema"],
                "additionalProperties": False,
            },
            "trigger": {
                "type": "object",
                "properties": {
                    "query_signals": _array({"type": "string"}),
                    "question_types": _array({"type": "string"}),
                    "intents": _array({"type": "string"}),
                },
                "required": ["query_signals", "question_types", "intents"],
                "additionalProperties": False,
            },
            "applicability": {
                "type": "object",
                "properties": {
                    "document_types": _array({"type": "string"}),
                    "scope": {"type": "string"},
                    "non_scope": {"type": "string"},
                },
                "required": ["document_types", "scope", "non_scope"],
                "additionalProperties": False,
            },
            "inputs": {
                "type": "object",
                "properties": {
                    "required": _array({"$ref": _schema_id("input_field")}),
                    "optional": _array({"$ref": _schema_id("input_field")}),
                },
                "required": ["required", "optional"],
                "additionalProperties": False,
            },
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string"},
                        "type": {"type": "string"},
                        "goal": {"type": "string"},
                        "depends_on": _array({"type": "string"}),
                        "io": {
                            "type": "object",
                            "properties": {
                                "inputs": _array({"type": "string"}),
                                "outputs": _array({"$ref": _schema_id("output_field")}),
                            },
                            "required": ["inputs", "outputs"],
                            "additionalProperties": False,
                        },
                        "executor": {
                            "type": "object",
                            "properties": {
                                "mode": {"type": "string", "enum": ["tool", "llm"]},
                                "tool": {"type": ["string", "null"]},
                                "template_id": {"type": ["string", "null"]},
                                "allowed_tools": _array({"type": "string"}),
                                "config": {"type": "object", "additionalProperties": True},
                            },
                            "required": ["mode", "allowed_tools"],
                            "additionalProperties": False,
                        },
                        "constraints": {
                            "type": "object",
                            "properties": {
                                "must_use_evidence": {"type": "boolean"},
                                "max_tokens": {"type": ["integer", "null"]},
                            },
                            "required": ["must_use_evidence"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["step_id", "type", "goal", "depends_on", "io", "executor", "constraints"],
                    "additionalProperties": False,
                },
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "answer_schema": {"type": "object", "additionalProperties": True},
                    "must_include": _array({"type": "string"}),
                },
                "required": ["answer_schema", "must_include"],
                "additionalProperties": False,
            },
            "validators": _array({"$ref": _schema_id("validator_ref")}),
            "provenance": {
                "type": "object",
                "properties": {
                    "source_cases": _array({"type": "string"}),
                    "review": {
                        "type": "object",
                        "properties": {
                            "review_status": {"type": "string", "enum": ["unreviewed", "approved", "rejected"]},
                            "reviewer": {"type": "string"},
                            "reviewed_at": {"type": "string"},
                        },
                        "required": ["review_status", "reviewer", "reviewed_at"],
                        "additionalProperties": False,
                    },
                },
                "required": ["source_cases", "review"],
                "additionalProperties": False,
            },
        },
        "required": [
            "rule_id",
            "name",
            "status",
            "version",
            "trigger",
            "applicability",
            "inputs",
            "steps",
            "outputs",
            "validators",
            "provenance"
        ],
        "additionalProperties": False,
    }

    document_record = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("document_record"),
        "type": "object",
        "properties": {
            "doc_id": {"type": "string"},
            "doc_type": {"type": "string"},
            "title": {"type": "string"},
            "language": {"type": "string"},
            "source": {"type": "string"},
            "tags": _array({"type": "string"}),
            "metadata": {"type": "object", "additionalProperties": True},
        },
        "required": ["doc_id", "doc_type", "title", "language", "source"],
        "additionalProperties": False,
    }

    document_bundle_record = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("document_bundle_record"),
        "type": "object",
        "properties": {
            "bundle_id": {"type": "string"},
            "scenario_id": {"type": "string"},
            "documents": _array({"$ref": _schema_id("document_record")}),
            "facts": {"type": "object", "additionalProperties": True},
            "evidence_refs": _array({"$ref": _schema_id("evidence_ref")}),
            "created_at": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": ["bundle_id", "scenario_id", "documents", "facts", "evidence_refs", "created_at", "notes"],
        "additionalProperties": False,
    }

    gold_answer = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("gold_answer"),
        "type": "object",
        "properties": {
            "answer_text": {"type": "string"},
            "decision": {"type": "string"},
            "confidence": {"type": "number"},
            "explanation": {"type": "string"},
            "evidence_snippet_ids": _array({"type": "string"}),
        },
        "required": ["answer_text", "decision", "confidence", "explanation", "evidence_snippet_ids"],
        "additionalProperties": False,
    }

    case_step = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("case_step"),
        "type": "object",
        "properties": {
            "step_id": {"type": "string"},
            "description": {"type": "string"},
            "tool": {"type": "string"},
            "inputs": {"type": "object", "additionalProperties": True},
            "expected_output": {"type": "object", "additionalProperties": True},
            "evidence_snippet_ids": _array({"type": "string"}),
        },
        "required": ["step_id", "description", "tool", "inputs", "expected_output", "evidence_snippet_ids"],
        "additionalProperties": False,
    }

    case_record = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("case_record"),
        "type": "object",
        "properties": {
            "case_id": {"type": "string"},
            "scenario_id": {"type": "string"},
            "title": {"type": "string"},
            "question": {"$ref": _schema_id("question_struct")},
            "document_bundle_id": {"type": "string"},
            "gold_answer": {"$ref": _schema_id("gold_answer")},
            "solution_steps": _array({"$ref": _schema_id("case_step")}),
            "linked_rule_ids": _array({"type": "string"}),
            "review_status": {"type": "string"},
            "reviewer": {"type": "string"},
            "created_at": {"type": "string"},
        },
        "required": [
            "case_id",
            "scenario_id",
            "title",
            "question",
            "document_bundle_id",
            "gold_answer",
            "solution_steps",
            "linked_rule_ids",
            "review_status",
            "reviewer",
            "created_at"
        ],
        "additionalProperties": False,
    }

    review_checklist_item = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("review_checklist_item"),
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
            "label": {"type": "string"},
            "status": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["item_id", "label", "status", "note"],
        "additionalProperties": False,
    }

    review_task = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("review_task"),
        "type": "object",
        "properties": {
            "review_task_id": {"type": "string"},
            "target_type": {"type": "string"},
            "target_id": {"type": "string"},
            "status": {"type": "string"},
            "assignee": {"type": "string"},
            "checklist": _array({"$ref": _schema_id("review_checklist_item")}),
            "comments": _array({"type": "string"}),
            "created_at": {"type": "string"},
            "completed_at": {"type": ["string", "null"]},
        },
        "required": ["review_task_id", "target_type", "target_id", "status", "assignee", "checklist", "comments", "created_at"],
        "additionalProperties": False,
    }

    feedback_record = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("feedback_record"),
        "type": "object",
        "properties": {
            "feedback_id": {"type": "string"},
            "trace_id": {"type": "string"},
            "case_id": {"type": ["string", "null"]},
            "rule_ids": _array({"type": "string"}),
            "route_decision": {"type": "string"},
            "feedback_type": {"type": "string"},
            "payload": {"type": "object", "additionalProperties": True},
            "created_at": {"type": "string"},
        },
        "required": ["feedback_id", "trace_id", "case_id", "rule_ids", "route_decision", "feedback_type", "payload", "created_at"],
        "additionalProperties": False,
    }

    execution_trace_record = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("execution_trace_record"),
        "type": "object",
        "properties": {
            "trace_id": {"type": "string"},
            "created_at": {"type": "string"},
            "route_decision": {"type": "string"},
            "status": {"type": "string"},
            "question_struct": {"type": "object", "additionalProperties": True},
            "retrieval": {"type": "object", "additionalProperties": True},
            "resolved_inputs": {"type": "object", "additionalProperties": True},
            "step_contracts": _array({"type": "object", "additionalProperties": True}),
            "step_results": _array({"type": "object", "additionalProperties": True}),
            "validator_results": _array({"type": "object", "additionalProperties": True}),
            "final_result": {"type": ["object", "null"], "additionalProperties": True},
            "failure_reason": {"type": ["string", "null"]},
            "composition_plan": {"type": ["object", "null"], "additionalProperties": True},
            "composition_trace": {"type": ["object", "null"], "additionalProperties": True},
            "feedback": _array({"$ref": _schema_id("feedback_record")}),
        },
        "required": [
            "trace_id",
            "created_at",
            "route_decision",
            "status",
            "question_struct",
            "retrieval",
            "resolved_inputs",
            "step_contracts",
            "step_results",
            "validator_results",
            "final_result",
            "failure_reason"
        ],
        "additionalProperties": False,
    }

    simulation_dataset = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("simulation_dataset"),
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "scenario_name": {"type": "string"},
            "generated_at": {"type": "string"},
            "question": {"$ref": _schema_id("question_struct")},
            "document_bundle": {"$ref": _schema_id("document_bundle_record")},
            "case_record": {"$ref": _schema_id("case_record")},
            "rule_pool": _array({"$ref": _schema_id("rule")}),
            "review_task": {"$ref": _schema_id("review_task")},
            "execution_trace": {"$ref": _schema_id("execution_trace_record")},
        },
        "required": [
            "dataset_id",
            "scenario_name",
            "generated_at",
            "question",
            "document_bundle",
            "case_record",
            "rule_pool",
            "review_task",
            "execution_trace"
        ],
        "additionalProperties": False,
    }

    dataset_manifest = {
        "$schema": SCHEMA_URI,
        "$id": _schema_id("dataset_manifest"),
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string"},
            "scenario_name": {"type": "string"},
            "generated_at": {"type": "string"},
            "files": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "required": ["dataset_id", "scenario_name", "generated_at", "files"],
        "additionalProperties": False,
    }

    return {
        "input_field": input_field,
        "output_field": output_field,
        "evidence_ref": evidence_ref,
        "validator_ref": validator_ref,
        "question_struct": question_struct,
        "rule": rule,
        "document_record": document_record,
        "document_bundle_record": document_bundle_record,
        "gold_answer": gold_answer,
        "case_step": case_step,
        "case_record": case_record,
        "review_checklist_item": review_checklist_item,
        "review_task": review_task,
        "feedback_record": feedback_record,
        "execution_trace_record": execution_trace_record,
        "simulation_dataset": simulation_dataset,
        "dataset_manifest": dataset_manifest,
    }


def write_formal_schemas(output_dir: str | Path = DEFAULT_SCHEMA_DIR) -> dict[str, Any]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    registry = build_schema_registry()
    file_map: dict[str, str] = {}

    for name, schema in registry.items():
        path = root / _schema_id(name)
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
        file_map[name] = str(path)

    index_path = root / "schema_index.json"
    index_path.write_text(
        json.dumps(
            {
                "schema_count": len(registry),
                "schemas": {name: _schema_id(name) for name in registry},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {
        "output_dir": str(root.resolve()),
        "schema_count": len(registry),
        "files": file_map,
        "index_file": str(index_path),
    }


if __name__ == "__main__":
    print(json.dumps(write_formal_schemas(), ensure_ascii=False, indent=2))
