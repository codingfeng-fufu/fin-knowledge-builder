from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from ..schema import Rule
from .task_context import TaskContext


@dataclass(slots=True)
class RuleBinding:
    binding_id: str
    rule_id: str
    rule_kind: str
    rule_family: str
    retrieval_score: int
    binding_score: int
    binding_status: str
    satisfied_slots: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    assumed_slots: list[str] = field(default_factory=list)
    conflicting_slots: list[str] = field(default_factory=list)
    context_refs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    eligible_for_direct_match: bool = False
    eligible_for_composition: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _context_fact_map(task_context: TaskContext) -> dict[str, dict[str, Any]]:
    return {
        fact.fact_id: {
            "status": fact.status,
            "evidence_refs": list(fact.evidence_refs),
        }
        for fact in task_context.fact_entries
    }


def bind_rule(
    rule: Rule,
    task_context: TaskContext,
    *,
    retrieval_score: int = 0,
    retrieval_reasons: list[str] | None = None,
    eligible_for_direct_match: bool = False,
    eligible_for_composition: bool = False,
) -> RuleBinding:
    fact_map = _context_fact_map(task_context)
    satisfied_slots: list[str] = []
    missing_slots: list[str] = []
    assumed_slots: list[str] = []
    conflicting_slots: list[str] = []
    context_refs: set[str] = set()

    for field in rule.inputs.required:
        fact = fact_map.get(field.key)
        if fact is None:
            missing_slots.append(field.key)
            continue
        if fact["status"] in {"conflicting"}:
            conflicting_slots.append(field.key)
            continue
        if fact["status"] == "missing":
            missing_slots.append(field.key)
            continue
        if fact["status"] == "assumed":
            assumed_slots.append(field.key)
        satisfied_slots.append(field.key)
        for ref in fact.get("evidence_refs", []):
            snippet_id = ref.get("snippet_id")
            doc_id = ref.get("doc_id")
            if snippet_id:
                context_refs.add(str(snippet_id))
            elif doc_id:
                context_refs.add(str(doc_id))

    for field in rule.inputs.optional:
        fact = fact_map.get(field.key)
        if fact is None:
            continue
        if fact["status"] == "assumed":
            assumed_slots.append(field.key)
        satisfied_slots.append(field.key)

    required_count = len(rule.inputs.required)
    binding_score = retrieval_score + len(satisfied_slots) * 4 - len(missing_slots) * 3 - len(conflicting_slots) * 5 - len(assumed_slots) * 1
    required_keys = {f.key for f in rule.inputs.required}
    has_required_assumed = bool(required_keys & set(assumed_slots))
    if not missing_slots and not conflicting_slots and not has_required_assumed and len([field.key for field in rule.inputs.required if field.key in satisfied_slots]) == required_count:
        binding_status = "bindable"
    elif satisfied_slots or retrieval_score > 0:
        binding_status = "partially_bindable"
    else:
        binding_status = "unbindable"

    reasons = [] if retrieval_reasons is None else list(retrieval_reasons)
    reasons.append(f"binding_status={binding_status}")
    if missing_slots:
        reasons.append(f"missing_slots={missing_slots}")
    if assumed_slots:
        reasons.append(f"assumed_slots={assumed_slots}")
    if conflicting_slots:
        reasons.append(f"conflicting_slots={conflicting_slots}")

    return RuleBinding(
        binding_id=f"binding_{uuid4().hex[:12]}",
        rule_id=rule.rule_id,
        rule_kind=rule.rule_kind,
        rule_family=rule.rule_family,
        retrieval_score=retrieval_score,
        binding_score=binding_score,
        binding_status=binding_status,
        satisfied_slots=satisfied_slots,
        missing_slots=missing_slots,
        assumed_slots=assumed_slots,
        conflicting_slots=conflicting_slots,
        context_refs=sorted(context_refs),
        reasons=reasons,
        eligible_for_direct_match=eligible_for_direct_match,
        eligible_for_composition=eligible_for_composition,
    )


def bind_rules_from_trace(
    *,
    task_context: TaskContext,
    rule_by_id: dict[str, Rule],
    candidate_payloads: list[dict[str, Any]],
) -> list[RuleBinding]:
    bindings: list[RuleBinding] = []
    for payload in candidate_payloads:
        rule_id = payload.get("rule_id")
        if rule_id not in rule_by_id:
            continue
        bindings.append(
            bind_rule(
                rule_by_id[rule_id],
                task_context,
                retrieval_score=int(payload.get("score", 0)),
                retrieval_reasons=list(payload.get("reasons", [])),
                eligible_for_direct_match=bool(payload.get("eligible_for_direct_match", False)),
                eligible_for_composition=bool(payload.get("eligible_for_composition", False)),
            )
        )
    return bindings
