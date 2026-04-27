from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from ..retrieval import MatchResult, retrieve_candidates, select_composable_candidates
from .rule_binding import RuleBinding
from ..schema import FailureRoute, QuestionStruct, Rule, SchemaError, Step, StepContract, ValidatorRef


class InputResolutionError(ValueError):
    """Raised when a required rule input or step reference cannot be resolved."""


class CompositionPlanError(ValueError):
    """Raised when retrieved atomic rules cannot form a legal composition plan."""


def complete_rule_inputs(rule: Rule, question: QuestionStruct, facts: dict[str, Any]) -> dict[str, Any]:
    input_pool = dict(facts)
    input_pool.update(question.extracted_inputs)
    return complete_rule_inputs_from_pool(rule, input_pool)


def complete_rule_inputs_from_pool(rule: Rule, input_pool: dict[str, Any]) -> dict[str, Any]:
    # Keys produced by LLM extract steps don't need to come from the pool
    llm_produced_keys = {
        output_field.key
        for step in rule.steps
        if step.executor.mode == "llm"
        for output_field in step.io.outputs
    }
    resolved: dict[str, Any] = {}
    for field in rule.inputs.required:
        if field.key in input_pool:
            resolved[field.key] = input_pool[field.key]
            continue
        if field.key in llm_produced_keys:
            continue  # will be resolved by an extract step at execution time
        raise InputResolutionError(f"missing required input: {field.key}")

    for field in rule.inputs.optional:
        if field.key in input_pool:
            resolved[field.key] = input_pool[field.key]

    return resolved


def topological_steps(rule: Rule) -> list[Step]:
    step_map = {step.step_id: step for step in rule.steps}
    indegree = {step.step_id: 0 for step in rule.steps}
    adjacency: dict[str, list[str]] = {step.step_id: [] for step in rule.steps}

    for step in rule.steps:
        for dependency in step.depends_on:
            if dependency not in step_map:
                raise SchemaError(f"Step {step.step_id} depends on unknown step {dependency}")
            indegree[step.step_id] += 1
            adjacency[dependency].append(step.step_id)

    queue = deque(step_id for step_id, degree in indegree.items() if degree == 0)
    ordered_ids: list[str] = []

    while queue:
        step_id = queue.popleft()
        ordered_ids.append(step_id)
        for neighbor in adjacency[step_id]:
            indegree[neighbor] -= 1
            if indegree[neighbor] == 0:
                queue.append(neighbor)

    if len(ordered_ids) != len(rule.steps):
        raise SchemaError("Rule.steps contains a cycle")

    return [step_map[step_id] for step_id in ordered_ids]


def resolve_step_inputs(step: Step, resolved_inputs: dict[str, Any], state: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for reference in step.io.inputs:
        if reference.startswith("$input."):
            key = reference.split(".", 1)[1]
            if key not in resolved_inputs:
                raise InputResolutionError(f"missing input reference {reference}")
            values[key] = resolved_inputs[key]
            continue

        if reference.startswith("$step."):
            parts = reference.split(".")
            if len(parts) < 4 or parts[2] != "output":
                raise InputResolutionError(f"unsupported step reference {reference}")
            step_id = parts[1]
            key = parts[3]
            if step_id not in state or key not in state[step_id]:
                raise InputResolutionError(f"missing step reference {reference}")
            values[key] = state[step_id][key]
            continue

        raise InputResolutionError(f"unsupported input reference {reference}")

    return values


def _hints_for_step(rule: Rule, step: Step) -> list[str]:
    """Collect hints from rule.inputs.required for keys produced by this step."""
    produced_keys = {f.key for f in step.io.outputs}
    hints: list[str] = []
    for field in rule.inputs.required:
        if field.key in produced_keys:
            hints.extend(field.hints)
    return hints


def build_step_contract(
    trace_id: str,
    rule: Rule,
    step: Step,
    resolved_inputs: dict[str, Any],
    state: dict[str, dict[str, Any]],
    facts: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    validators: list[ValidatorRef],
    question_text: str | None = None,
    document_full_text: str | None = None,
    source_rule_ids: list[str] | None = None,
    composition_plan_id: str | None = None,
    composition_role: str | None = None,
    binding_map: dict[str, Any] | None = None,
    document_chunks: list[dict[str, Any]] | None = None,
) -> StepContract:
    step_inputs = resolve_step_inputs(step, resolved_inputs, state)
    output_schema = {
        "type": "object",
        "required": [field.key for field in step.io.outputs],
        "properties": {field.key: {"type": field.type} for field in step.io.outputs},
    }
    return StepContract(
        trace_id=trace_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        step_id=step.step_id,
        step_type=step.type,
        goal=step.goal,
        inputs=step_inputs,
        context={
            "question_text": question_text or "",
            "document_full_text": document_full_text or "",
            "facts": facts,
            "evidence_refs": evidence_refs,
            "document_chunks": document_chunks or [],
            "kg_subgraph": None,
        },
        constraints={
            "rules": ["structured_output_only", "error_validator_failure_stops_execution"],
            "allowed_actions": {
                "allowed_tools": step.executor.allowed_tools,
                "allowed_skills": [],
            },
            "output_schema": output_schema,
            "must_use_evidence": step.constraints.must_use_evidence,
            "hints": _hints_for_step(rule, step),
        },
        executor={
            "mode": step.executor.mode,
            "tool": step.executor.tool,
            "template_id": step.executor.template_id,
            "config": step.executor.config,
        },
        validation={
            "validators": [validator.validator_id for validator in validators],
            "on_failure": [
                FailureRoute("format_error", "abort", 1).to_dict(),
                FailureRoute("need_more_evidence", "ask_human", 1).to_dict(),
                FailureRoute("tool_error", "abort", 1).to_dict(),
            ],
        },
        source_rule_ids=[] if source_rule_ids is None else list(source_rule_ids),
        composition_plan_id=composition_plan_id,
        composition_role=composition_role,
        binding_map={} if binding_map is None else dict(binding_map),
    )


def _required_input_keys(rule: Rule) -> list[str]:
    return [field.key for field in rule.inputs.required]


def _output_keys(rule: Rule) -> list[str]:
    properties = rule.outputs.answer_schema.get("properties", {})
    if isinstance(properties, dict) and properties:
        return list(properties.keys())
    return [field.key for field in rule.steps[-1].io.outputs]


def _is_final_rule(rule: Rule) -> bool:
    output_keys = set(_output_keys(rule))
    return {"answer_text", "decision"}.issubset(output_keys)


def _infer_composition_role(rule: Rule) -> str:
    output_keys = set(_output_keys(rule))
    if {"answer_text", "decision"}.issubset(output_keys):
        return "final_decision"
    if any(key.endswith("required") for key in output_keys):
        return "condition_check"
    if any(key.endswith("breached") or key.endswith("open") for key in output_keys):
        return "derive_value"
    return "derive_value"


def _binding_map_for_rule(
    rule: Rule,
    facts: dict[str, Any],
    extracted_inputs: dict[str, Any],
    produced_by: dict[str, str],
) -> tuple[dict[str, Any], list[str]] | None:
    binding_map: dict[str, Any] = {}
    dependencies: list[str] = []
    for key in _required_input_keys(rule):
        if key in extracted_inputs:
            binding_map[key] = {"source": "question_input", "key": key}
            continue
        if key in facts:
            binding_map[key] = {"source": "fact", "key": key}
            continue
        if key in produced_by:
            dependency_rule_id = produced_by[key]
            binding_map[key] = {"source": "rule_output", "rule_id": dependency_rule_id, "key": key}
            if dependency_rule_id not in dependencies:
                dependencies.append(dependency_rule_id)
            continue
        return None
    return binding_map, dependencies


def _composition_candidate_sort_key(candidate: MatchResult) -> tuple[int, int, int, int]:
    rule = candidate.rule
    return (
        1 if not _is_final_rule(rule) else 0,
        candidate.score,
        len(_output_keys(rule)),
        candidate.signal_hits,
    )


def _build_family_plan(
    family: str,
    family_matches: list[MatchResult],
    question: QuestionStruct,
    facts: dict[str, Any],
) -> dict[str, Any] | None:
    remaining = list(sorted(family_matches, key=_composition_candidate_sort_key, reverse=True))
    if not remaining:
        return None

    plan_nodes: list[dict[str, Any]] = []
    produced_by: dict[str, str] = {}
    source_rule_ids: list[str] = []

    while remaining:
        eligible: list[tuple[MatchResult, dict[str, Any], list[str]]] = []
        for candidate in remaining:
            binding = _binding_map_for_rule(candidate.rule, facts, question.extracted_inputs, produced_by)
            if binding is None:
                continue
            binding_map, dependencies = binding
            eligible.append((candidate, binding_map, dependencies))

        if not eligible:
            break

        candidate, binding_map, dependencies = sorted(
            eligible,
            key=lambda item: _composition_candidate_sort_key(item[0]),
            reverse=True,
        )[0]
        rule = candidate.rule
        node = {
            "node_id": f"node_{len(plan_nodes) + 1}",
            "rule_id": rule.rule_id,
            "composition_role": _infer_composition_role(rule),
            "depends_on_rule_ids": dependencies,
            "binding_map": binding_map,
            "required_inputs": _required_input_keys(rule),
            "output_keys": _output_keys(rule),
        }
        plan_nodes.append(node)
        source_rule_ids.append(rule.rule_id)
        for key in node["output_keys"]:
            produced_by[key] = rule.rule_id
        remaining = [item for item in remaining if item.rule.rule_id != rule.rule_id]
        if _is_final_rule(rule):
            return {
                "composition_plan_id": f"compose_{family}_{len(source_rule_ids)}",
                "rule_family": family,
                "composition_pattern": "derive_then_decide",
                "source_rule_ids": source_rule_ids,
                "plan_dag": plan_nodes,
            }

    return None


def build_composition_plan(
    question: QuestionStruct,
    candidates: list[MatchResult],
    facts: dict[str, Any],
) -> dict[str, Any] | None:
    families: dict[str, list[MatchResult]] = defaultdict(list)
    for candidate in candidates:
        families[candidate.rule.rule_family].append(candidate)

    ranked_families = sorted(
        families.items(),
        key=lambda item: max(candidate.score for candidate in item[1]),
        reverse=True,
    )
    for family, family_matches in ranked_families:
        plan = _build_family_plan(family, family_matches, question, facts)
        if plan is not None:
            return plan
    return None


def compile_route(
    question: QuestionStruct,
    rules: list[Rule],
    facts: dict[str, Any],
    min_signal_hits: int = 1,
    retrieval_top_k: int = 5,
    candidates: list[MatchResult] | None = None,
) -> dict[str, Any]:
    ranked_candidates = retrieve_candidates(
        rules,
        question,
        min_signal_hits=min_signal_hits,
        top_k=retrieval_top_k,
        facts=facts,
    ) if candidates is None else candidates

    direct_match = next((candidate for candidate in ranked_candidates if candidate.eligible_for_direct_match), None)
    if direct_match is not None:
        return {
            "route_decision": "direct_match",
            "selected_rule_id": direct_match.rule.rule_id,
            "composition_plan": None,
            "failure_reason": None,
        }

    composable_candidates = select_composable_candidates(ranked_candidates)
    composition_plan = build_composition_plan(question, composable_candidates, facts)
    if composition_plan is not None:
        return {
            "route_decision": "rule_composable",
            "selected_rule_id": None,
            "composition_plan": composition_plan,
            "failure_reason": None,
        }

    failure_reason = "composition_failed" if composable_candidates else "no_direct_or_composable_rule"
    return {
        "route_decision": "exploration",
        "selected_rule_id": None,
        "composition_plan": None,
        "failure_reason": failure_reason,
    }


def _binding_to_match_result(binding: RuleBinding, rule_by_id: dict[str, Rule]) -> MatchResult:
    rule = rule_by_id[binding.rule_id]
    return MatchResult(
        rule=rule,
        score=binding.retrieval_score,
        reasons=list(binding.reasons),
        signal_hits=max(1, binding.retrieval_score // 8),
        eligible_for_direct_match=binding.eligible_for_direct_match,
        eligible_for_composition=binding.eligible_for_composition,
    )


def compile_route_from_bindings(
    bindings: list[RuleBinding],
    question: QuestionStruct,
    rule_by_id: dict[str, Rule],
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Binding-aware route decision. Requires all required inputs to be grounded for direct_match."""

    # Compute all keys that can be produced by any candidate rule.
    # Used to distinguish document-level facts from intermediate computed values.
    all_produced_keys: set[str] = set()
    for b in bindings:
        if b.rule_id in rule_by_id:
            all_produced_keys.update(_output_keys(rule_by_id[b.rule_id]))

    def _document_level_uncertain(b: RuleBinding) -> list[str]:
        """Slots that are missing/assumed AND are not produced by any other candidate rule."""
        uncertain = set(b.missing_slots) | set(b.assumed_slots)
        return [slot for slot in uncertain if slot not in all_produced_keys]

    def _has_grounded_context(b: RuleBinding) -> bool:
        """True if at least one satisfied slot is grounded (not assumed)."""
        return len(b.satisfied_slots) > len(b.assumed_slots)

    # Step A: direct_match — must be bindable (no assumed required inputs) + eligible
    direct = next(
        (b for b in bindings if b.binding_status == "bindable" and b.eligible_for_direct_match),
        None,
    )
    if direct is not None:
        return {
            "route_decision": "direct_match",
            "selected_rule_id": direct.rule_id,
            "composition_plan": None,
            "failure_reason": None,
            "missing_slots": [],
        }

    # Step B: rule_composable — atomic bindings eligible for composition.
    # Include rules that are either fully bindable OR have only inter-rule dependencies
    # (all uncertain slots are produced by other rules in the candidate set, not document gaps).
    atomic_composable = [
        b for b in bindings
        if b.eligible_for_composition
        and b.rule_id in rule_by_id
        and (b.binding_status == "bindable" or not _document_level_uncertain(b))
    ]
    if atomic_composable:
        composable_candidates = [_binding_to_match_result(b, rule_by_id) for b in atomic_composable]
        plan = build_composition_plan(question, composable_candidates, facts)
        if plan is not None:
            return {
                "route_decision": "rule_composable",
                "selected_rule_id": None,
                "composition_plan": plan,
                "failure_reason": None,
                "missing_slots": [],
            }

    # Step C: needs_more_context — has relevant rules but grounded context is insufficient.
    # Only trigger when:
    #   - at least some grounded context exists (not all assumed / totally empty)
    #   - some document-level inputs are missing or assumed from defaults
    partial = [
        b for b in bindings
        if b.binding_status == "partially_bindable"
        and _has_grounded_context(b)
        and _document_level_uncertain(b)
    ]
    if partial:
        best = max(partial, key=lambda b: (b.binding_score, b.retrieval_score))
        true_missing = _document_level_uncertain(best)
        return {
            "route_decision": "needs_more_context",
            "selected_rule_id": best.rule_id,
            "composition_plan": None,
            "failure_reason": "insufficient_grounded_context",
            "missing_slots": true_missing,
        }

    # Step D: exploration
    failure_reason = "composition_failed" if atomic_composable else "no_direct_or_composable_rule"
    return {
        "route_decision": "exploration",
        "selected_rule_id": None,
        "composition_plan": None,
        "failure_reason": failure_reason,
        "missing_slots": [],
    }
