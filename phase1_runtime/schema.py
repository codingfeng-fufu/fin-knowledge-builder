from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


class SchemaError(ValueError):
    """Raised when a fixture or payload does not satisfy the local schema."""


def _expect_mapping(data: Any, where: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise SchemaError(f"{where} must be an object")
    return data


def _expect_list(data: Any, where: str) -> list[Any]:
    if not isinstance(data, list):
        raise SchemaError(f"{where} must be a list")
    return data


def _expect_str(data: Any, where: str) -> str:
    if not isinstance(data, str):
        raise SchemaError(f"{where} must be a string")
    return data


def _expect_bool(data: Any, where: str) -> bool:
    if not isinstance(data, bool):
        raise SchemaError(f"{where} must be a boolean")
    return data


def _expect_enum(data: Any, choices: set[str], where: str) -> str:
    value = _expect_str(data, where)
    if value not in choices:
        raise SchemaError(f"{where} must be one of {sorted(choices)}")
    return value


def _expect_dict_of_any(data: Any, where: str) -> dict[str, Any]:
    mapping = _expect_mapping(data, where)
    return {str(key): value for key, value in mapping.items()}


def _load_json(path: Path) -> dict[str, Any]:
    return _expect_mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


@dataclass(slots=True)
class InputField:
    key: str
    type: str
    description: str
    hints: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InputField":
        mapping = _expect_mapping(data, "InputField")
        return cls(
            key=_expect_str(mapping.get("key"), "InputField.key"),
            type=_expect_enum(
                mapping.get("type"),
                {"string", "number", "boolean", "date", "object", "array"},
                "InputField.type",
            ),
            description=_expect_str(mapping.get("description"), "InputField.description"),
            hints=[str(h) for h in mapping.get("hints", [])],
        )


@dataclass(slots=True)
class OutputField:
    key: str
    type: str
    description: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OutputField":
        mapping = _expect_mapping(data, "OutputField")
        return cls(
            key=_expect_str(mapping.get("key"), "OutputField.key"),
            type=_expect_enum(
                mapping.get("type"),
                {"string", "number", "boolean", "date", "object", "array"},
                "OutputField.type",
            ),
            description=_expect_str(mapping.get("description"), "OutputField.description"),
        )


@dataclass(slots=True)
class StepIO:
    inputs: list[str]
    outputs: list[OutputField]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepIO":
        mapping = _expect_mapping(data, "Step.io")
        return cls(
            inputs=[_expect_str(item, "Step.io.inputs[]") for item in _expect_list(mapping.get("inputs"), "Step.io.inputs")],
            outputs=[OutputField.from_dict(item) for item in _expect_list(mapping.get("outputs"), "Step.io.outputs")],
        )


@dataclass(slots=True)
class StepExecutor:
    mode: str
    tool: str | None = None
    template_id: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepExecutor":
        mapping = _expect_mapping(data, "Step.executor")
        mode = _expect_enum(mapping.get("mode"), {"tool", "llm"}, "Step.executor.mode")
        return cls(
            mode=mode,
            tool=mapping.get("tool"),
            template_id=mapping.get("template_id"),
            allowed_tools=[_expect_str(item, "Step.executor.allowed_tools[]") for item in _expect_list(mapping.get("allowed_tools", []), "Step.executor.allowed_tools")],
            config=_expect_dict_of_any(mapping.get("config", {}), "Step.executor.config"),
        )


@dataclass(slots=True)
class StepConstraints:
    must_use_evidence: bool
    max_tokens: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepConstraints":
        mapping = _expect_mapping(data, "Step.constraints")
        max_tokens = mapping.get("max_tokens")
        if max_tokens is not None and not isinstance(max_tokens, int):
            raise SchemaError("Step.constraints.max_tokens must be an integer when provided")
        return cls(
            must_use_evidence=_expect_bool(mapping.get("must_use_evidence"), "Step.constraints.must_use_evidence"),
            max_tokens=max_tokens,
        )


@dataclass(slots=True)
class Step:
    step_id: str
    type: str
    goal: str
    depends_on: list[str]
    io: StepIO
    executor: StepExecutor
    constraints: StepConstraints

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        mapping = _expect_mapping(data, "Step")
        return cls(
            step_id=_expect_str(mapping.get("step_id"), "Step.step_id"),
            type=_expect_enum(
                mapping.get("type"),
                {"extract", "retrieve", "transform", "filter", "join", "dedup", "compute", "graph", "judge", "aggregate", "explain"},
                "Step.type",
            ),
            goal=_expect_str(mapping.get("goal"), "Step.goal"),
            depends_on=[_expect_str(item, "Step.depends_on[]") for item in _expect_list(mapping.get("depends_on", []), "Step.depends_on")],
            io=StepIO.from_dict(mapping.get("io")),
            executor=StepExecutor.from_dict(mapping.get("executor")),
            constraints=StepConstraints.from_dict(mapping.get("constraints")),
        )


@dataclass(slots=True)
class RuleTrigger:
    query_signals: list[str]
    question_types: list[str]
    intents: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleTrigger":
        mapping = _expect_mapping(data, "Rule.trigger")
        return cls(
            query_signals=[_expect_str(item, "Rule.trigger.query_signals[]") for item in _expect_list(mapping.get("query_signals"), "Rule.trigger.query_signals")],
            question_types=[_expect_str(item, "Rule.trigger.question_types[]") for item in _expect_list(mapping.get("question_types"), "Rule.trigger.question_types")],
            intents=[_expect_str(item, "Rule.trigger.intents[]") for item in _expect_list(mapping.get("intents"), "Rule.trigger.intents")],
        )


@dataclass(slots=True)
class RuleApplicability:
    document_types: list[str]
    scope: str
    non_scope: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleApplicability":
        mapping = _expect_mapping(data, "Rule.applicability")
        return cls(
            document_types=[_expect_str(item, "Rule.applicability.document_types[]") for item in _expect_list(mapping.get("document_types"), "Rule.applicability.document_types")],
            scope=_expect_str(mapping.get("scope"), "Rule.applicability.scope"),
            non_scope=_expect_str(mapping.get("non_scope"), "Rule.applicability.non_scope"),
        )


@dataclass(slots=True)
class RuleInputs:
    required: list[InputField]
    optional: list[InputField]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleInputs":
        mapping = _expect_mapping(data, "Rule.inputs")
        return cls(
            required=[InputField.from_dict(item) for item in _expect_list(mapping.get("required"), "Rule.inputs.required")],
            optional=[InputField.from_dict(item) for item in _expect_list(mapping.get("optional", []), "Rule.inputs.optional")],
        )


@dataclass(slots=True)
class RuleOutputs:
    answer_schema: dict[str, Any]
    must_include: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleOutputs":
        mapping = _expect_mapping(data, "Rule.outputs")
        return cls(
            answer_schema=_expect_dict_of_any(mapping.get("answer_schema"), "Rule.outputs.answer_schema"),
            must_include=[_expect_str(item, "Rule.outputs.must_include[]") for item in _expect_list(mapping.get("must_include"), "Rule.outputs.must_include")],
        )


@dataclass(slots=True)
class ValidatorRef:
    validator_id: str
    target: str
    severity: str
    params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidatorRef":
        mapping = _expect_mapping(data, "ValidatorRef")
        return cls(
            validator_id=_expect_str(mapping.get("validator_id"), "ValidatorRef.validator_id"),
            target=_expect_str(mapping.get("target"), "ValidatorRef.target"),
            severity=_expect_enum(mapping.get("severity"), {"error", "warn"}, "ValidatorRef.severity"),
            params=_expect_dict_of_any(mapping.get("params", {}), "ValidatorRef.params"),
        )


@dataclass(slots=True)
class ReviewInfo:
    review_status: str
    reviewer: str
    reviewed_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewInfo":
        mapping = _expect_mapping(data, "Rule.provenance.review")
        return cls(
            review_status=_expect_enum(mapping.get("review_status"), {"unreviewed", "approved", "rejected"}, "Rule.provenance.review.review_status"),
            reviewer=_expect_str(mapping.get("reviewer"), "Rule.provenance.review.reviewer"),
            reviewed_at=_expect_str(mapping.get("reviewed_at"), "Rule.provenance.review.reviewed_at"),
        )


@dataclass(slots=True)
class Provenance:
    source_cases: list[str]
    review: ReviewInfo

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Provenance":
        mapping = _expect_mapping(data, "Rule.provenance")
        return cls(
            source_cases=[_expect_str(item, "Rule.provenance.source_cases[]") for item in _expect_list(mapping.get("source_cases"), "Rule.provenance.source_cases")],
            review=ReviewInfo.from_dict(mapping.get("review")),
        )


@dataclass(slots=True)
class RuleComposition:
    pattern: str
    source_rule_ids: list[str]
    binding_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleComposition":
        mapping = _expect_mapping(data, "Rule.composition")
        return cls(
            pattern=_expect_str(mapping.get("pattern"), "Rule.composition.pattern"),
            source_rule_ids=[
                _expect_str(item, "Rule.composition.source_rule_ids[]")
                for item in _expect_list(mapping.get("source_rule_ids", []), "Rule.composition.source_rule_ids")
            ],
            binding_schema=_expect_dict_of_any(mapping.get("binding_schema", {}), "Rule.composition.binding_schema"),
        )


@dataclass(slots=True)
class Rule:
    rule_id: str
    name: str
    status: str
    version: str
    trigger: RuleTrigger
    applicability: RuleApplicability
    inputs: RuleInputs
    steps: list[Step]
    outputs: RuleOutputs
    validators: list[ValidatorRef]
    provenance: Provenance
    rule_kind: str = "composite"
    rule_family: str = ""
    composition: RuleComposition | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        mapping = _expect_mapping(data, "Rule")
        steps = [Step.from_dict(item) for item in _expect_list(mapping.get("steps"), "Rule.steps")]
        if not steps:
            raise SchemaError("Rule.steps must not be empty")

        rule_id = _expect_str(mapping.get("rule_id"), "Rule.rule_id")
        composition_data = mapping.get("composition")
        rule_family = mapping.get("rule_family") or rule_id
        return cls(
            rule_id=rule_id,
            name=_expect_str(mapping.get("name"), "Rule.name"),
            status=_expect_enum(mapping.get("status"), {"draft", "candidate", "published", "deprecated"}, "Rule.status"),
            version=_expect_str(mapping.get("version"), "Rule.version"),
            trigger=RuleTrigger.from_dict(mapping.get("trigger")),
            applicability=RuleApplicability.from_dict(mapping.get("applicability")),
            inputs=RuleInputs.from_dict(mapping.get("inputs")),
            steps=steps,
            outputs=RuleOutputs.from_dict(mapping.get("outputs")),
            validators=[ValidatorRef.from_dict(item) for item in _expect_list(mapping.get("validators"), "Rule.validators")],
            provenance=Provenance.from_dict(mapping.get("provenance")),
            rule_kind=_expect_enum(mapping.get("rule_kind", "composite"), {"atomic", "composite"}, "Rule.rule_kind"),
            rule_family=_expect_str(rule_family, "Rule.rule_family"),
            composition=None if composition_data is None else RuleComposition.from_dict(composition_data),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuestionStruct:
    question_text: str
    question_types: list[str]
    intents: list[str]
    document_types: list[str]
    extracted_inputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuestionStruct":
        mapping = _expect_mapping(data, "QuestionStruct")
        return cls(
            question_text=_expect_str(mapping.get("question_text"), "QuestionStruct.question_text"),
            question_types=[_expect_str(item, "QuestionStruct.question_types[]") for item in _expect_list(mapping.get("question_types"), "QuestionStruct.question_types")],
            intents=[_expect_str(item, "QuestionStruct.intents[]") for item in _expect_list(mapping.get("intents"), "QuestionStruct.intents")],
            document_types=[_expect_str(item, "QuestionStruct.document_types[]") for item in _expect_list(mapping.get("document_types"), "QuestionStruct.document_types")],
            extracted_inputs=_expect_dict_of_any(mapping.get("extracted_inputs", {}), "QuestionStruct.extracted_inputs"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class EvidenceRef:
    doc_id: str
    locator: dict[str, Any]
    snippet_id: str
    text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        mapping = _expect_mapping(data, "EvidenceRef")
        return cls(
            doc_id=_expect_str(mapping.get("doc_id"), "EvidenceRef.doc_id"),
            locator=_expect_dict_of_any(mapping.get("locator", {}), "EvidenceRef.locator"),
            snippet_id=_expect_str(mapping.get("snippet_id"), "EvidenceRef.snippet_id"),
            text=_expect_str(mapping.get("text"), "EvidenceRef.text"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FailureRoute:
    failure_type: str
    action: str
    max_attempts: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StepContract:
    trace_id: str
    rule_id: str
    rule_version: str
    step_id: str
    step_type: str
    goal: str
    inputs: dict[str, Any]
    context: dict[str, Any]
    constraints: dict[str, Any]
    executor: dict[str, Any]
    validation: dict[str, Any]
    source_rule_ids: list[str] = field(default_factory=list)
    composition_plan_id: str | None = None
    composition_role: str | None = None
    binding_map: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_rule(path: str | Path) -> Rule:
    return Rule.from_dict(_load_json(Path(path)))


def load_question(path: str | Path) -> QuestionStruct:
    return QuestionStruct.from_dict(_load_json(Path(path)))


def load_document_bundle(path: str | Path) -> tuple[dict[str, Any], list[EvidenceRef]]:
    data = _load_json(Path(path))
    facts = _expect_dict_of_any(data.get("facts", {}), "DocumentBundle.facts")
    evidence_refs = [EvidenceRef.from_dict(item) for item in _expect_list(data.get("evidence_refs", []), "DocumentBundle.evidence_refs")]
    return facts, evidence_refs
