from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from ..kimi_llm_executor import KimiTransport
from ..retrieval import MatchResult, get_active_embedding_backend_metadata, retrieve_candidates
from ..schema import QuestionStruct, Rule, ValidatorRef
from .compiler import (
    InputResolutionError,
    build_step_contract,
    compile_route,
    compile_route_from_bindings,
    complete_rule_inputs,
    complete_rule_inputs_from_pool,
    topological_steps,
)
from .executors import execute_llm, execute_tool
from .trace_store import TraceStore
from .validation import ValidationError, run_validator


@dataclass(slots=True)
class RuntimeResult:
    trace_id: str
    trace_path: Path
    route_decision: str
    status: str
    final_result: dict[str, Any] | None
    matched_rule_id: str | None
    failure_reason: str | None
    composition_pattern: str | None = None
    source_rule_ids: list[str] = field(default_factory=list)
    composition_plan: dict[str, Any] | None = None
    missing_slots: list[str] = field(default_factory=list)


class Phase1Runtime:
    def __init__(self, trace_dir: str | Path, min_signal_hits: int = 1, retrieval_top_k: int = 5) -> None:
        self.trace_store = TraceStore(trace_dir)
        self.min_signal_hits = min_signal_hits
        self.retrieval_top_k = retrieval_top_k

    @staticmethod
    def _missing_slots_from_error(message: str | None) -> list[str]:
        if not message:
            return []
        patterns = [
            re.compile(r"missing required input: (?P<field>[A-Za-z0-9_]+)"),
            re.compile(r"compare_numeric requires numeric input for (?P<field>[A-Za-z0-9_]+), got None"),
        ]
        slots: list[str] = []
        for pattern in patterns:
            match = pattern.search(message)
            if match:
                field = str(match.group("field")).strip()
                if field and field not in slots:
                    slots.append(field)
        return slots

    def run(
        self,
        question: QuestionStruct,
        rules: list[Rule],
        facts: dict[str, Any],
        evidence_refs: list[Any],
        *,
        retrieval_fact_keys: set[str] | list[str] | None = None,
        task_context: Any | None = None,
        rule_bindings: list[Any] | None = None,
        document_chunks: list[dict[str, Any]] | None = None,
        document_full_text: str | None = None,
        kimi_client: KimiTransport | None = None,
    ) -> RuntimeResult:
        trace_id = f"trace_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"
        embedding_backend = get_active_embedding_backend_metadata()
        candidates = retrieve_candidates(
            rules,
            question,
            min_signal_hits=self.min_signal_hits,
            top_k=self.retrieval_top_k,
            facts=facts,
            evidence_refs=evidence_refs,
            retrieval_fact_keys=retrieval_fact_keys,
        )
        trace: dict[str, Any] = {
            "trace_id": trace_id,
            "created_at": datetime.now(UTC).isoformat(),
            "question_struct": question.to_dict(),
            "route_decision": None,
            "status": "running",
            "retrieval": {
                "candidates": [candidate.to_dict() for candidate in candidates],
                "min_signal_hits": self.min_signal_hits,
                "embedding_backend": embedding_backend,
                "diagnostics": (
                    dict(candidates[0].metadata.get("retrieval_diagnostics", {}))
                    if candidates and isinstance(candidates[0].metadata.get("retrieval_diagnostics", {}), dict)
                    else {}
                ),
            },
            "resolved_inputs": {},
            "step_contracts": [],
            "step_results": [],
            "validator_results": [],
            "final_result": None,
            "failure_reason": None,
            "composition_plan": None,
            "composition_trace": None,
            "feedback": [],
        }
        route = compile_route(
            question=question,
            rules=rules,
            facts=facts,
            min_signal_hits=self.min_signal_hits,
            retrieval_top_k=self.retrieval_top_k,
            candidates=candidates,
        )
        if rule_bindings is not None:
            rule_by_id_for_bindings = {rule.rule_id: rule for rule in rules}
            route = compile_route_from_bindings(rule_bindings, question, rule_by_id_for_bindings, facts)
        trace["route_decision"] = route["route_decision"]
        rule_by_id = {rule.rule_id: rule for rule in rules}
        candidate_by_rule_id = {candidate.rule.rule_id: candidate for candidate in candidates}
        serializable_evidence_refs = [item.to_dict() if hasattr(item, "to_dict") else item for item in evidence_refs]

        if route["route_decision"] == "direct_match":
            rule = rule_by_id[route["selected_rule_id"]]
            match = candidate_by_rule_id[rule.rule_id]
            trace["retrieval"]["matched_rule_id"] = rule.rule_id
            trace["retrieval"]["score"] = match.score
            trace["retrieval"]["reasons"] = match.reasons
            try:
                resolved_inputs = complete_rule_inputs(rule, question, facts)
                trace["resolved_inputs"] = resolved_inputs
                final_result = self._execute_rule(
                    trace=trace,
                    trace_id=trace_id,
                    rule=rule,
                    question_text=question.question_text,
                    document_full_text=document_full_text,
                    resolved_inputs=resolved_inputs,
                    facts=facts,
                    evidence_refs=serializable_evidence_refs,
                    document_chunks=document_chunks or [],
                    kimi_client=kimi_client,
                )
                trace["final_result"] = final_result
                trace["status"] = "completed"
                trace_path = self.trace_store.write(trace_id, trace)
                return RuntimeResult(
                    trace_id=trace_id,
                    trace_path=trace_path,
                    route_decision="direct_match",
                    status="completed",
                    final_result=final_result,
                    matched_rule_id=rule.rule_id,
                    failure_reason=None,
                )
            except (InputResolutionError, ValidationError, ValueError) as exc:
                missing_slots = self._missing_slots_from_error(str(exc))
                trace["status"] = "failed"
                trace["failure_reason"] = str(exc)
                trace["retrieval"]["missing_slots"] = list(missing_slots)
                trace_path = self.trace_store.write(trace_id, trace)
                return RuntimeResult(
                    trace_id=trace_id,
                    trace_path=trace_path,
                    route_decision="direct_match",
                    status="failed",
                    final_result=None,
                    matched_rule_id=rule.rule_id,
                    failure_reason=str(exc),
                    missing_slots=missing_slots,
                )

        if route["route_decision"] == "rule_composable":
            plan = route["composition_plan"]
            trace["composition_plan"] = plan
            trace["retrieval"]["source_rule_ids"] = plan["source_rule_ids"]
            trace["retrieval"]["composition_pattern"] = plan["composition_pattern"]
            try:
                final_result = self._execute_composition(
                    trace=trace,
                    trace_id=trace_id,
                    composition_plan=plan,
                    rule_by_id=rule_by_id,
                    question=question,
                    facts=facts,
                    evidence_refs=serializable_evidence_refs,
                    document_chunks=document_chunks or [],
                    document_full_text=document_full_text,
                    kimi_client=kimi_client,
                )
                trace["final_result"] = final_result
                trace["status"] = "completed"
                trace_path = self.trace_store.write(trace_id, trace)
                return RuntimeResult(
                    trace_id=trace_id,
                    trace_path=trace_path,
                    route_decision="rule_composable",
                    status="completed",
                    final_result=final_result,
                    matched_rule_id=None,
                    failure_reason=None,
                    composition_pattern=plan["composition_pattern"],
                    source_rule_ids=list(plan["source_rule_ids"]),
                    composition_plan=plan,
                )
            except (InputResolutionError, ValidationError, ValueError) as exc:
                missing_slots = self._missing_slots_from_error(str(exc))
                trace["status"] = "failed"
                trace["failure_reason"] = str(exc)
                trace["retrieval"]["missing_slots"] = list(missing_slots)
                trace["feedback"].append(self._build_feedback(trace_id, route["route_decision"], "composition_failure", plan.get("source_rule_ids", []), {"reason": str(exc)}))
                trace_path = self.trace_store.write(trace_id, trace)
                return RuntimeResult(
                    trace_id=trace_id,
                    trace_path=trace_path,
                    route_decision="rule_composable",
                    status="failed",
                    final_result=None,
                    matched_rule_id=None,
                    failure_reason=str(exc),
                    composition_pattern=plan["composition_pattern"],
                    source_rule_ids=list(plan["source_rule_ids"]),
                    composition_plan=plan,
                    missing_slots=missing_slots,
                )

        trace["status"] = "failed"
        trace["failure_reason"] = route["failure_reason"]
        feedback_type = "composition_failure" if route["failure_reason"] == "composition_failed" else "missed_rule"
        trace["feedback"].append(self._build_feedback(trace_id, "exploration", feedback_type, [], {"reason": route["failure_reason"]}))
        trace_path = self.trace_store.write(trace_id, trace)

        if route["route_decision"] == "needs_more_context":
            return RuntimeResult(
                trace_id=trace_id,
                trace_path=trace_path,
                route_decision="needs_more_context",
                status="needs_more_context",
                final_result=None,
                matched_rule_id=route.get("selected_rule_id"),
                failure_reason=route["failure_reason"],
                missing_slots=list(route.get("missing_slots", [])),
            )

        return RuntimeResult(
            trace_id=trace_id,
            trace_path=trace_path,
            route_decision="exploration",
            status="failed",
            final_result=None,
            matched_rule_id=None,
            failure_reason=route["failure_reason"],
        )

    def _execute_composition(
        self,
        trace: dict[str, Any],
        trace_id: str,
        composition_plan: dict[str, Any],
        rule_by_id: dict[str, Rule],
        question: QuestionStruct,
        facts: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
        document_chunks: list[dict[str, Any]] | None = None,
        document_full_text: str | None = None,
        kimi_client: Any | None = None,
    ) -> dict[str, Any]:
        input_pool = dict(facts)
        input_pool.update(question.extracted_inputs)
        composition_trace = {
            "composition_plan_id": composition_plan["composition_plan_id"],
            "source_rule_ids": list(composition_plan["source_rule_ids"]),
            "composition_pattern": composition_plan["composition_pattern"],
            "rule_results": [],
            "final_decision": None,
            "uncertainty": None,
        }

        final_result: dict[str, Any] | None = None
        resolved_inputs_by_rule: dict[str, dict[str, Any]] = {}
        for node in composition_plan["plan_dag"]:
            rule = rule_by_id[node["rule_id"]]
            resolved_inputs = complete_rule_inputs_from_pool(rule, input_pool)
            resolved_inputs_by_rule[rule.rule_id] = resolved_inputs
            rule_result = self._execute_rule(
                trace=trace,
                trace_id=trace_id,
                rule=rule,
                question_text=question.question_text,
                document_full_text=document_full_text,
                resolved_inputs=resolved_inputs,
                facts=facts,
                evidence_refs=evidence_refs,
                source_rule_ids=composition_plan["source_rule_ids"],
                composition_plan_id=composition_plan["composition_plan_id"],
                composition_role=node["composition_role"],
                binding_map=node["binding_map"],
                document_chunks=document_chunks or [],
                kimi_client=kimi_client,
            )
            input_pool.update(rule_result)
            final_result = rule_result
            composition_trace["rule_results"].append(
                {
                    "rule_id": rule.rule_id,
                    "composition_role": node["composition_role"],
                    "depends_on_rule_ids": node["depends_on_rule_ids"],
                    "binding_map": node["binding_map"],
                    "output_keys": sorted(rule_result.keys()),
                }
            )

        trace["resolved_inputs"] = resolved_inputs_by_rule
        trace["composition_trace"] = composition_trace
        if final_result is None:
            raise ValueError("composition produced no final result")
        composition_trace["final_decision"] = final_result.get("decision")
        return final_result

    def _execute_rule(
        self,
        trace: dict[str, Any],
        trace_id: str,
        rule: Rule,
        question_text: str | None,
        document_full_text: str | None,
        resolved_inputs: dict[str, Any],
        facts: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
        source_rule_ids: list[str] | None = None,
        composition_plan_id: str | None = None,
        composition_role: str | None = None,
        binding_map: dict[str, Any] | None = None,
        document_chunks: list[dict[str, Any]] | None = None,
        kimi_client: Any | None = None,
    ) -> dict[str, Any]:
        state: dict[str, dict[str, Any]] = {}
        last_step_id: str | None = None
        for step in topological_steps(rule):
            # Accumulate evidence_refs from all previously executed LLM steps.
            # Tool steps (compare_numeric, boolean_gate, etc.) use this as their
            # evidence context instead of the base empty evidence_refs list.
            accumulated_evidence: list[dict[str, Any]] = []
            for step_output in state.values():
                refs = step_output.get("evidence_refs")
                if isinstance(refs, list):
                    accumulated_evidence.extend(refs)
            effective_evidence_refs = accumulated_evidence if accumulated_evidence else list(evidence_refs)
            step_validators = [validator for validator in rule.validators if validator.target in {f"step:{step.step_id}", "rule"}]
            contract = build_step_contract(
                trace_id=trace_id,
                rule=rule,
                step=step,
                resolved_inputs=resolved_inputs,
                state=state,
                facts=facts,
                evidence_refs=effective_evidence_refs,
                validators=step_validators,
                question_text=question_text,
                document_full_text=document_full_text,
                source_rule_ids=source_rule_ids,
                composition_plan_id=composition_plan_id,
                composition_role=composition_role,
                binding_map=binding_map,
                document_chunks=document_chunks or [],
            )
            trace["step_contracts"].append(contract.to_dict())

            mode = contract.executor["mode"]
            if mode == "tool":
                step_result = execute_tool(
                    tool_name=contract.executor.get("tool"),
                    inputs=contract.inputs,
                    context=contract.context,
                    config=contract.executor.get("config", {}),
                )
            elif mode == "llm":
                step_schema = contract.constraints["output_schema"]
                # Include facts as fallback values in step_state so that
                # tests with pre-loaded seed facts work without a Kimi API key.
                fallback_facts = {k: v for k, v in facts.items() if v is not None}
                step_state_with_fallback = {
                    **fallback_facts,
                    **{k: v for step_state in state.values() for k, v in step_state.items()},
                }
                try:
                    step_result = execute_llm(
                        goal=contract.goal,
                        context={
                            **contract.context,
                            "step_state": step_state_with_fallback,
                        },
                        output_schema=step_schema,
                        constraints=contract.constraints,
                        kimi_client=kimi_client,
                    )
                except RuntimeError as exc:
                    raise ValueError(f"LLM step '{step.step_id}' failed: {exc}") from exc
            else:
                raise ValueError(f"unsupported executor mode {mode}")

            step_schema = contract.constraints["output_schema"]
            synthetic_validators = list(step_validators)
            # evidence.required only applies to LLM steps (extraction steps that must cite sources).
            # Tool steps (compare_numeric, boolean_gate etc.) derive values computationally
            # and are not expected to carry document evidence references.
            if contract.constraints.get("must_use_evidence") and mode == "llm":
                synthetic_validators.append(
                    ValidatorRef(
                        validator_id="evidence.required",
                        target=f"step:{step.step_id}",
                        severity="error",
                        params={},
                    )
                )

            validation_results = self._run_validators(synthetic_validators, step_result, step_schema)
            trace["validator_results"].extend(validation_results)

            state[step.step_id] = step_result
            last_step_id = step.step_id
            trace["step_results"].append({"rule_id": rule.rule_id, "step_id": step.step_id, "output": step_result})

        if last_step_id is None:
            raise ValueError("rule produced no executable steps")

        final_result = state[last_step_id]
        final_validators = [validator for validator in rule.validators if validator.target in {"final", "rule"}]
        final_validators.append(
            ValidatorRef(
                validator_id="must_include",
                target="final",
                severity="error",
                params={"fields": rule.outputs.must_include},
            )
        )
        final_validation_results = self._run_validators(final_validators, final_result, rule.outputs.answer_schema)
        trace["validator_results"].extend(final_validation_results)
        return final_result

    def _build_feedback(
        self,
        trace_id: str,
        route_decision: str,
        feedback_type: str,
        rule_ids: list[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "feedback_id": f"feedback_{uuid4().hex[:12]}",
            "trace_id": trace_id,
            "case_id": None,
            "rule_ids": list(rule_ids),
            "route_decision": route_decision,
            "feedback_type": feedback_type,
            "payload": payload,
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _run_validators(
        self,
        validators: list[ValidatorRef],
        payload: dict[str, Any],
        schema: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for validator in validators:
            results.append(run_validator(validator, payload, schema))
        return results
