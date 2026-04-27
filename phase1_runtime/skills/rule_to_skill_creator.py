from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Callable

from ..runtime_core import RuleBinding, TaskContext
from ..schema import Rule
from .kimi_skill_creator_client import build_kimi_llm_generate


SkillCreatorLLM = Callable[[dict[str, Any]], dict[str, Any]]
SKILL_CREATOR_ROOT = Path.home() / ".claude" / "skills" / "skill-creator"
SKILL_CREATOR_SKILL_MD = SKILL_CREATOR_ROOT / "SKILL.md"
SKILL_CREATOR_VALIDATOR = SKILL_CREATOR_ROOT / "scripts" / "quick_validate.py"


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized[:63] or "generated-skill"


def _skill_type(rule: Rule) -> str:
    step_types = {step.type for step in rule.steps}
    tool_names = {step.executor.tool for step in rule.steps if step.executor.tool}
    output_keys = set(rule.outputs.answer_schema.get("properties", {}).keys())
    if "compute" in step_types or "compare_numeric" in tool_names:
        return "calculation"
    if {"answer_text", "decision"}.issubset(output_keys):
        return "decision"
    if "extract" in step_types:
        return "extraction"
    return "direct_answer"


def _executor_label(step) -> str:
    if step.executor.mode == "tool":
        return f"tool:{step.executor.tool}"
    return "llm"


def _load_skill_creator_reference() -> str | None:
    if not SKILL_CREATOR_SKILL_MD.exists():
        return None
    try:
        return SKILL_CREATOR_SKILL_MD.read_text(encoding="utf-8")
    except Exception:
        return None


@dataclass(slots=True)
class SkillArtifact:
    skill_name: str
    title: str
    description: str
    skill_md: str
    references: dict[str, str] = field(default_factory=dict)
    scripts: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def file_map(self) -> dict[str, str]:
        files = {"SKILL.md": self.skill_md}
        files.update({f"references/{name}": content for name, content in self.references.items()})
        files.update({f"scripts/{name}": content for name, content in self.scripts.items()})
        return files

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "title": self.title,
            "description": self.description,
            "skill_md": self.skill_md,
            "references": dict(self.references),
            "scripts": dict(self.scripts),
            "metadata": dict(self.metadata),
        }


def build_skill_creator_request(
    rule: Rule,
    task_context: TaskContext,
    rule_binding: RuleBinding,
) -> dict[str, Any]:
    suggested_name = _slugify(f"{rule.rule_family}-{_skill_type(rule)}")
    skill_creator_reference = _load_skill_creator_reference()
    return {
        "system_prompt": (
            "You are converting a reusable rule and a bound task context into a reusable runtime skill artifact. "
            "Follow the installed Anthropic skill-creator methodology when available. "
            "The artifact must remain a runtime skill, not a permanent rule-library asset."
        ),
        "user_prompt": (
            "Create a reusable skill artifact from this rule and current binding. "
            "The skill should describe how to complete this kind of task, not answer one specific question."
        ),
        "query": task_context.question_text,
        "rule": rule.to_dict(),
        "task_context": task_context.to_dict(),
        "rule_binding": rule_binding.to_dict(),
        "skill_creator_reference_md": skill_creator_reference,
        "constraints": {
            "must_include_sections": [
                "When to use",
                "Inputs",
                "Workflow",
                "Validation",
            ],
            "required_files": ["SKILL.md"],
            "suggested_skill_name": suggested_name,
        },
    }


def _render_skill_md(
    *,
    skill_name: str,
    description: str,
    rule: Rule,
    task_context: TaskContext,
    rule_binding: RuleBinding,
) -> str:
    required_inputs = [field.key for field in rule.inputs.required]
    optional_inputs = [field.key for field in rule.inputs.optional]
    workflow_lines = []
    for index, step in enumerate(rule.steps, start=1):
        workflow_lines.append(
            f"{index}. `{step.step_id}`: {step.goal} Executor `{_executor_label(step)}`. "
            f"Inputs: {', '.join(step.io.inputs) or '-'}"
        )

    validation_lines = [validator.validator_id for validator in rule.validators]
    body = f"""---
name: {skill_name}
description: {description}
---

# {rule.name}

## When to use

- Use for questions that belong to `{rule.rule_family}`.
- Current binding status: `{rule_binding.binding_status}`.
- Current context status: `{task_context.context_status}`.

## Inputs

- Required: {', '.join(required_inputs) or '-'}
- Optional: {', '.join(optional_inputs) or '-'}
- Satisfied in current context: {', '.join(rule_binding.satisfied_slots) or '-'}
- Missing in current context: {', '.join(rule_binding.missing_slots) or '-'}
- Assumed in current context: {', '.join(rule_binding.assumed_slots) or '-'}

## Workflow

{chr(10).join(workflow_lines)}

## Validation

- Validators: {', '.join(validation_lines) or '-'}
- Retrieval score: {rule_binding.retrieval_score}
- Binding score: {rule_binding.binding_score}
- Reasons: {', '.join(rule_binding.reasons) or '-'}
"""
    return body


def compile_rule_to_reusable_skill(
    rule: Rule,
    task_context: TaskContext,
    rule_binding: RuleBinding,
    *,
    llm_generate: SkillCreatorLLM | None = None,
    include_references: bool = True,
) -> SkillArtifact:
    request = build_skill_creator_request(rule, task_context, rule_binding)
    suggested_name = request["constraints"]["suggested_skill_name"]
    description = f"Reusable skill compiled from rule `{rule.rule_id}` for `{rule.rule_family}` tasks."
    references = {}
    scripts = {}
    generator_backend = "template"
    generator_error = None
    skill_md = _render_skill_md(
        skill_name=suggested_name,
        description=description,
        rule=rule,
        task_context=task_context,
        rule_binding=rule_binding,
    )

    active_llm_generate = llm_generate
    if active_llm_generate is None:
        try:
            active_llm_generate = build_kimi_llm_generate()
            generator_backend = "kimi"
        except Exception as exc:
            generator_error = str(exc)

    if active_llm_generate is not None:
        try:
            generated = active_llm_generate(request)
            suggested_name = _slugify(str(generated.get("skill_name", suggested_name)))
            description = str(generated.get("description", description))
            skill_md = str(generated.get("skill_md", skill_md))
            references = dict(generated.get("references", {}))
            scripts = dict(generated.get("scripts", {}))
        except Exception as exc:
            generator_backend = "template"
            generator_error = str(exc)

    if include_references and not references:
        references = {
            "source-rule.json": json.dumps(rule.to_dict(), ensure_ascii=False, indent=2),
            "bound-context.json": json.dumps(task_context.to_dict(), ensure_ascii=False, indent=2),
            "rule-binding.json": json.dumps(rule_binding.to_dict(), ensure_ascii=False, indent=2),
        }

    return SkillArtifact(
        skill_name=suggested_name,
        title=rule.name,
        description=description,
        skill_md=skill_md,
        references=references,
        scripts=scripts,
        metadata={
            "source_rule_id": rule.rule_id,
            "skill_type": _skill_type(rule),
            "binding_status": rule_binding.binding_status,
            "context_status": task_context.context_status,
            "generator_backend": generator_backend,
            "generator_error": generator_error,
        },
    )


def materialize_skill_artifact(artifact: SkillArtifact, output_root: str | Path) -> Path:
    root = Path(output_root) / artifact.skill_name
    root.mkdir(parents=True, exist_ok=True)
    for relative_path, content in artifact.file_map().items():
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def validate_skill_artifact(path: str | Path) -> dict[str, Any] | None:
    root = Path(path)
    if not SKILL_CREATOR_VALIDATOR.exists():
        return None
    result = subprocess.run(
        ["python3", str(SKILL_CREATOR_VALIDATOR), str(root)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    message = (result.stdout or result.stderr or "").strip()
    return {
        "validator": "anthropic_skill_creator.quick_validate",
        "ok": result.returncode == 0,
        "message": message,
    }
