from __future__ import annotations

from pathlib import Path
from typing import Any

from ..factory import record_workspace_run
from ..kimi_llm_executor import KimiTransport
from ..analysis import build_orchestration_view, poll_multi_agent_exploration_task
from ..registry.registry_store import DEFAULT_DB_PATH
from ..retrieval import get_active_embedding_backend_metadata
from ..runtime_core.executors import build_research_rating_target_audit_answer
from .product_catalog import (
    DECISION_TEXT_MAP,
    DEFAULT_PRODUCT_WORK_DIR,
    PRODUCT_SCENARIOS,
    ROUTE_GUIDANCE_MAP,
    ROUTE_TITLE_MAP,
    build_expert_view,
    get_workspace_contract,
    normalize_materials,
)
from .workspace_runtime import (
    _build_workspace_runtime_inputs,
    _prepare_workspace_rules,
    _resolve_workspace_scenario_and_parse,
    _run_workspace_runtime,
    _scenario_rule_ids,
    _scenario_seed_bundle,
)
from .workspace_support import (
    _build_exploration_links,
    _build_exploration_provisional_answer,
    _prepare_exploration_provisional_assets,
    _build_workspace_feedback_defaults,
    _build_workspace_feedback_payload,
    _build_workspace_solution_view,
    _complete_workspace_exploration_runtime,
    _display_decision_text,
    _display_rule_binding,
    _grounded_retrieval_fact_keys,
    _looks_like_placeholder_exploration_answer,
    _present_missing_slots,
    _prepare_super_agent_assets,
    _resolve_workspace_answer,
    _resolve_workspace_exploration_runtime,
    _run_workspace_super_agent,
    _select_primary_binding,
    _should_allow_shortcut,
    _summarize_uploaded_materials,
    _super_agent_max_turns,
)


# In-memory cache for pending exploration workspace context.
# Keyed by exploration task_id, populated when solve_workspace_request triggers
# exploration non-blockingly, cleared when solve_workspace_exploration_poll is called.
_pending_exploration_cache: dict[str, dict[str, Any]] = {}


def _looks_like_equity_valuation_audit(question_text: str, scenario_id: str) -> bool:
    if scenario_id != "equity_research":
        return False
    lowered = question_text.lower()
    return (
        ("python" in lowered or "代码" in question_text)
        and "收盘价" in question_text
        and "评级" in question_text
        and any(token in question_text for token in ("PE", "PB", "每股盈利", "每股净资产", "估值简表", "复算", "核验"))
    )


def _joined_text_materials(materials: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for item in materials:
        content = str(item.get("content") or "").strip()
        if content:
            blocks.append(content)
    return "\n\n".join(blocks)
def _fallback_answer(route_decision: str, missing_slots: list[str] | None = None) -> tuple[str, str]:
    if route_decision == "needs_more_context":
        slots_hint = "、".join(missing_slots) if missing_slots else "部分关键字段"
        return (
            "needs_more_context",
            f"系统已识别到相关规则，但以下字段未能从文档中获取：{slots_hint}。请补充相关材料后重新提交。",
        )
    if route_decision == "exploration":
        return (
            "needs_review",
            "当前没有稳定规则可直接给出建议，系统已进入探索路径，建议人工复核并记录反馈。",
        )
    return (
        "needs_review",
        "当前结果未完整生成，建议人工复核后再继续沉淀规则。",
    )


def solve_workspace_request(
    question_text: str,
    materials: list[dict[str, Any]] | None = None,
    scenario_id: str | None = None,
    work_dir: str | Path = DEFAULT_PRODUCT_WORK_DIR,
    db_path: str | Path = DEFAULT_DB_PATH,
    kimi_client: KimiTransport | None = None,
    use_live_kimi: bool = True,
    run_live_super_agent: bool = False,
    super_agent_backend: str = "builtin",
    coding_agent_check_command: str | None = None,
    coding_agent_review_with_agent: bool = False,
    coding_agent_provider: str = "auto",
    exploration_backend: str = "multi_agent_exploration",
    exploration_use_llm: bool = True,
    exploration_mode: str = "emergent",
    block_until_complete: bool = False,
) -> dict[str, Any]:
    effective_kimi_client = kimi_client
    if effective_kimi_client is None and not use_live_kimi:
        def _disabled_kimi_client(_payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("live kimi disabled for this request")
        effective_kimi_client = _disabled_kimi_client

    normalized_materials = normalize_materials(materials)
    effective_question, scenario_reason, document_parse_result, parsed_materials = _resolve_workspace_scenario_and_parse(
        question_text=question_text,
        materials=normalized_materials,
        scenario_id=scenario_id,
    )
    scenario_id = str(scenario_reason.get("selected_scenario_id") or scenario_id)
    super_agent_max_turns = _super_agent_max_turns(effective_question)
    seed_bundle = _scenario_seed_bundle(scenario_id)
    rules, unique_required_inputs = _prepare_workspace_rules(
        question_text=effective_question,
        scenario_id=scenario_id,
        db_path=db_path,
    )
    runtime_inputs = _build_workspace_runtime_inputs(
        effective_question=effective_question,
        scenario_id=scenario_id,
        parsed_materials=parsed_materials,
        seed_bundle=seed_bundle,
        required_inputs=unique_required_inputs,
        rules=rules,
        db_path=db_path,
    )
    parser_bundle = runtime_inputs["parser_bundle"]
    documents = runtime_inputs["documents"]
    evidence_refs = runtime_inputs["evidence_refs"]
    evidence_packets = runtime_inputs["evidence_packets"]
    document_chunks = runtime_inputs["document_chunks"]
    document_full_text = runtime_inputs["document_full_text"]
    retrieval_fact_keys = runtime_inputs["retrieval_fact_keys"]
    task_context = runtime_inputs["task_context"]
    rule_by_id = runtime_inputs["rule_by_id"]
    rule_bindings = runtime_inputs["rule_bindings"]
    rule_bindings_payload = runtime_inputs["rule_bindings_payload"]

    trace_dir = Path(work_dir) / "workspace_runtime" / scenario_id
    trace_dir.mkdir(parents=True, exist_ok=True)
    runtime_result, trace_payload, similar_cases, shortcut_case = _run_workspace_runtime(
        effective_question=effective_question,
        scenario_id=scenario_id,
        normalized_materials=normalized_materials,
        rules=rules,
        parser_bundle=parser_bundle,
        evidence_refs=evidence_refs,
        retrieval_fact_keys=retrieval_fact_keys,
        task_context=task_context,
        rule_bindings=rule_bindings,
        document_chunks=document_chunks,
        document_full_text=document_full_text,
        effective_kimi_client=effective_kimi_client,
        trace_dir=trace_dir,
        db_path=db_path,
    )
    if (
        _looks_like_equity_valuation_audit(effective_question, scenario_id)
        and any("每股盈利" in str(item.get("content") or "") for item in normalized_materials)
        and (
            runtime_result.route_decision != "direct_match"
            or runtime_result.final_result is None
            or str(runtime_result.final_result.get("decision")) == "needs_review"
        )
    ):
        audit_result = build_research_rating_target_audit_answer(
            {},
            {
                "question_text": effective_question,
                "document_full_text": _joined_text_materials(normalized_materials),
                "document_chunks": document_chunks,
                "evidence_refs": evidence_packets,
                "facts": parser_bundle["facts"],
            },
            {},
        )
        runtime_result.route_decision = "direct_match"
        runtime_result.status = "completed"
        runtime_result.matched_rule_id = "equity_research.rating_target_audit.v1"
        runtime_result.final_result = {
            "decision": audit_result["decision"],
            "answer_text": audit_result["answer_text"],
            "evidence_refs": audit_result["evidence_refs"],
        }
        trace_payload["route_decision"] = "direct_match"
        trace_payload["status"] = "completed"
        trace_payload["final_result"] = dict(runtime_result.final_result)
        trace_payload.setdefault("retrieval", {})
        trace_payload["retrieval"]["matched_rule_id"] = runtime_result.matched_rule_id
    primary_binding = _select_primary_binding(rule_bindings)
    super_agent_assets = _prepare_super_agent_assets(
        primary_binding=primary_binding,
        rule_by_id=rule_by_id,
        task_context=task_context,
        runtime_result=runtime_result,
        work_dir=work_dir,
        effective_question=effective_question,
        parser_bundle=parser_bundle,
        super_agent_max_turns=super_agent_max_turns,
        super_agent_backend=super_agent_backend,
        coding_agent_check_command=coding_agent_check_command,
        coding_agent_review_with_agent=coding_agent_review_with_agent,
        coding_agent_provider=coding_agent_provider,
    )
    runtime_skill_spec_preview = super_agent_assets["runtime_skill_spec_preview"]
    runtime_skill_artifact = super_agent_assets["runtime_skill_artifact"]
    super_agent_handoff = super_agent_assets["super_agent_handoff"]

    final_decision, final_answer, evidence_packets = _resolve_workspace_answer(
        runtime_result=runtime_result,
        route_decision=runtime_result.route_decision,
        evidence_packets=evidence_packets,
    )
    final_answer, answer_engine, super_agent_result = _run_workspace_super_agent(
        runtime_skill_artifact=runtime_skill_artifact,
        super_agent_handoff=super_agent_handoff,
        run_live_super_agent=run_live_super_agent,
        kimi_client=kimi_client,
        effective_question=effective_question,
        work_dir=work_dir,
        task_context=task_context,
        parser_bundle=parser_bundle,
        super_agent_max_turns=super_agent_max_turns,
        effective_kimi_client=effective_kimi_client,
        super_agent_backend=super_agent_backend,
        coding_agent_check_command=coding_agent_check_command,
        coding_agent_review_with_agent=coding_agent_review_with_agent,
        coding_agent_provider=coding_agent_provider,
        final_answer=final_answer,
    )

    exploration_runtime = _resolve_workspace_exploration_runtime(
        trace_id=runtime_result.trace_id,
        route_decision=runtime_result.route_decision,
        runtime_status=runtime_result.status,
        scenario_id=scenario_id,
        effective_question=effective_question,
        final_decision=final_decision,
        failure_reason=trace_payload.get("failure_reason"),
        parser_bundle=parser_bundle,
        documents=documents,
        document_chunks=document_chunks,
        evidence_packets=evidence_packets,
        rules=rules,
        matched_rule_id=runtime_result.matched_rule_id,
        source_rule_ids=list(runtime_result.source_rule_ids),
        fallback_rule_ids=_scenario_rule_ids(scenario_id),
        exploration_backend=exploration_backend,
        exploration_use_llm=exploration_use_llm,
        exploration_mode=exploration_mode,
        block_until_complete=block_until_complete,
    )

    exploration_is_pending = isinstance(exploration_runtime, dict) and exploration_runtime.get("status") == "exploration_pending"
    if exploration_is_pending:
        task_id = (exploration_runtime.get("external_task") or {}).get("task_id")
        if task_id:
            _pending_exploration_cache[task_id] = {
                "work_dir": work_dir,
                "db_path": db_path,
                "trace_id": runtime_result.trace_id,
                "scenario_id": scenario_id,
                "effective_question": effective_question,
                "route_decision": runtime_result.route_decision,
                "runtime_status": runtime_result.status,
                "final_decision": final_decision,
                "matched_rule_id": runtime_result.matched_rule_id,
                "source_rule_ids": list(runtime_result.source_rule_ids),
                "fallback_rule_ids": _scenario_rule_ids(scenario_id),
                "failure_reason": trace_payload.get("failure_reason"),
                "parser_bundle": parser_bundle,
                "documents": documents,
                "document_chunks": document_chunks,
                "evidence_packets": evidence_packets,
                "rules": rules,
                "task_context": task_context,
                "runtime_result": runtime_result,
                "trace_payload": trace_payload,
                "similar_cases": similar_cases,
                "shortcut_case": shortcut_case,
                "super_agent_assets": super_agent_assets,
                "super_agent_max_turns": super_agent_max_turns,
                "super_agent_backend": super_agent_backend,
                "super_agent_result": super_agent_result,
                "coding_agent_check_command": coding_agent_check_command,
                "coding_agent_review_with_agent": coding_agent_review_with_agent,
                "coding_agent_provider": coding_agent_provider,
                "run_live_super_agent": run_live_super_agent,
                "kimi_client": kimi_client,
                "effective_kimi_client": effective_kimi_client,
                "normalized_materials": normalized_materials,
                "parsed_materials": parsed_materials,
                "document_parse_result": document_parse_result,
                "answer_engine": answer_engine,
                "seed_bundle": seed_bundle,
                "uploaded_materials_summary": _summarize_uploaded_materials(
                    normalized_materials=normalized_materials,
                    parsed_materials=parsed_materials,
                ),
                "embedding_backend": get_active_embedding_backend_metadata(),
            }
    if runtime_result.route_decision == "exploration" and runtime_skill_artifact is None and not exploration_is_pending:
        provisional_assets = _prepare_exploration_provisional_assets(
            exploration_runtime=exploration_runtime,
            work_dir=work_dir,
            trace_id=runtime_result.trace_id,
            effective_question=effective_question,
            task_context=task_context,
            parser_bundle=parser_bundle,
            super_agent_max_turns=super_agent_max_turns,
            super_agent_backend=super_agent_backend,
            coding_agent_check_command=coding_agent_check_command,
            coding_agent_review_with_agent=coding_agent_review_with_agent,
            coding_agent_provider=coding_agent_provider,
        )
        if provisional_assets["runtime_skill_artifact"] is not None and provisional_assets["super_agent_handoff"] is not None:
            runtime_skill_spec_preview = provisional_assets["runtime_skill_spec_preview"]
            runtime_skill_artifact = provisional_assets["runtime_skill_artifact"]
            super_agent_handoff = provisional_assets["super_agent_handoff"]
            final_answer, answer_engine, super_agent_result = _run_workspace_super_agent(
                runtime_skill_artifact=runtime_skill_artifact,
                super_agent_handoff=super_agent_handoff,
                run_live_super_agent=run_live_super_agent,
                kimi_client=kimi_client,
                effective_question=effective_question,
                work_dir=work_dir,
                task_context=task_context,
                parser_bundle=parser_bundle,
                super_agent_max_turns=super_agent_max_turns,
                effective_kimi_client=effective_kimi_client,
                super_agent_backend=super_agent_backend,
                coding_agent_check_command=coding_agent_check_command,
                coding_agent_review_with_agent=coding_agent_review_with_agent,
                coding_agent_provider=coding_agent_provider,
                final_answer=final_answer,
            )

    if (
        runtime_result.route_decision == "exploration"
        and not exploration_is_pending
        and _looks_like_placeholder_exploration_answer(final_answer)
    ):
        provisional_answer = _build_exploration_provisional_answer(
            question_text=effective_question,
            exploration_runtime=exploration_runtime,
        )
        if provisional_answer:
            final_answer = provisional_answer
            answer_engine = "runtime"

    feedback_defaults = _build_workspace_feedback_defaults(
        runtime_result=runtime_result,
        final_decision=final_decision,
        final_answer=final_answer,
        answer_engine=answer_engine,
        parser_bundle=parser_bundle,
        scenario_id=scenario_id,
        exploration_runtime=exploration_runtime,
    )

    solution_view = _build_workspace_solution_view(
        question_text=effective_question,
        documents=documents,
        evidence_packets=evidence_packets,
        parser_bundle=parser_bundle,
        trace_payload=trace_payload,
        final_decision=final_decision,
        final_answer=final_answer,
        answer_engine=answer_engine,
        route_decision=runtime_result.route_decision,
        runtime_result=runtime_result,
        feedback_defaults=feedback_defaults,
    )
    orchestration_view = build_orchestration_view(
        question_packet_preview=parser_bundle["question_packet_preview"],
        trace_payload=trace_payload,
        route_decision=runtime_result.route_decision,
        final_decision=final_decision,
        documents=documents,
        evidence_refs=evidence_packets,
        exploration_runtime=exploration_runtime,
    )
    solution_view["orchestration"] = orchestration_view

    uploaded_materials_summary = _summarize_uploaded_materials(
        normalized_materials=normalized_materials,
        parsed_materials=parsed_materials,
    )
    embedding_backend = get_active_embedding_backend_metadata()
    feedback_payload = _build_workspace_feedback_payload(
        feedback_defaults=feedback_defaults,
        effective_question=effective_question,
        parser_bundle=parser_bundle,
        task_context=task_context,
        document_parse_result=document_parse_result,
        exploration_runtime=exploration_runtime,
        runtime_result=runtime_result,
        trace_payload=trace_payload,
        embedding_backend=embedding_backend,
        runtime_skill_spec_preview=runtime_skill_spec_preview,
        answer_engine=answer_engine,
    )
    asset_pipeline = record_workspace_run(
        trace_id=runtime_result.trace_id,
        scenario_id=scenario_id,
        question_text=effective_question,
        route_decision=runtime_result.route_decision,
        runtime_status=runtime_result.status,
        final_decision=final_decision,
        final_answer=final_answer,
        parser_status=parser_bundle["parser_status"],
        parser_bridge_status="runtime_connected",
        question_packet_preview=parser_bundle["question_packet_preview"],
        document_packet_preview=parser_bundle["document_packet_preview"],
        fact_sheet=parser_bundle["fact_sheet"],
        documents=documents,
        evidence_refs=evidence_packets,
        task_context=task_context.to_dict(),
        rule_bindings=rule_bindings_payload,
        runtime_skill_spec_preview={} if runtime_skill_spec_preview is None else dict(runtime_skill_spec_preview),
        feedback_payload=feedback_payload,
        uploaded_materials=uploaded_materials_summary,
        unsupported_files=document_parse_result["unsupported_files"],
        embedding_backend=embedding_backend,
        retrieval_diagnostics=(trace_payload.get("retrieval", {}) or {}).get("diagnostics", {}),
        matched_rule_id=runtime_result.matched_rule_id,
        source_rule_ids=list(runtime_result.source_rule_ids),
        fallback_rule_ids=_scenario_rule_ids(scenario_id),
        trace_path=str(runtime_result.trace_path),
        db_path=db_path,
    )

    workspace_contract = get_workspace_contract()
    display_decision_text = _display_decision_text(
        final_decision=final_decision,
        final_answer=final_answer,
        answer_engine=answer_engine,
        route_decision=runtime_result.route_decision,
    )
    exploration_links = _build_exploration_links(exploration_runtime)
    return {
        "scenario_id": scenario_id,
        "scenario_title": PRODUCT_SCENARIOS[scenario_id]["title"],
        "scenario_description": PRODUCT_SCENARIOS[scenario_id]["description"],
        "question_text": effective_question,
        "documents": documents,
        "evidence_refs": evidence_packets,
        "fact_sheet": parser_bundle["fact_sheet"],
        "final_answer": final_answer,
        "final_decision": final_decision,
        "answer_engine": answer_engine,
        "decision_text": DECISION_TEXT_MAP.get(final_decision, final_decision),
        "display_decision_text": display_decision_text,
        "route_decision": runtime_result.route_decision,
        "matched_rule_id": runtime_result.matched_rule_id,
        "source_rule_ids": list(runtime_result.source_rule_ids),
        "missing_slots": list(getattr(runtime_result, "missing_slots", []) or []),
        "missing_slot_items": _present_missing_slots(list(getattr(runtime_result, "missing_slots", []) or [])),
        "route_title": ROUTE_TITLE_MAP.get(runtime_result.route_decision, runtime_result.route_decision),
        "route_explanation": ROUTE_GUIDANCE_MAP.get(runtime_result.route_decision, runtime_result.route_decision),
        "solution_view": solution_view,
        "feedback_defaults": feedback_defaults,
        "exploration_runtime": exploration_runtime,
        "exploration_links": exploration_links,
        "orchestration_view": orchestration_view,
        "flow_id": None,
        "input_mode": "expert_workspace",
        "workspace_contract": workspace_contract,
        "document_parser_contract": workspace_contract["document_parser_contract"],
        "expert_view": build_expert_view(
            scenario_id=scenario_id,
            question_text=effective_question,
            final_answer=final_answer,
            final_decision=final_decision,
            route_decision=runtime_result.route_decision,
        ),
        "question_packet_preview": parser_bundle["question_packet_preview"],
        "document_packet_preview": parser_bundle["document_packet_preview"],
        "context_packet": parser_bundle.get("context_packet", {}),
        "parser_status": parser_bundle["parser_status"],
        "parser_bridge_status": "runtime_connected",
        "task_context": task_context.to_dict(),
        "rule_bindings": rule_bindings_payload,
        "unsupported_files": document_parse_result["unsupported_files"],
        "uploaded_materials": uploaded_materials_summary,
        "embedding_backend": embedding_backend,
        "runtime_skill_spec_preview": runtime_skill_spec_preview,
        "runtime_skill_artifact": runtime_skill_artifact,
        "super_agent_handoff": super_agent_handoff,
        "super_agent_result": super_agent_result,
        "scenario_reason": scenario_reason,
        "trace_id": runtime_result.trace_id,
        "trace_path": str(runtime_result.trace_path),
        "asset_pipeline": asset_pipeline,
        "similar_cases": [m.to_dict() for m in similar_cases],
        "shortcut_case": shortcut_case.to_dict() if shortcut_case else None,
    }


def solve_workspace_exploration_poll(
    *,
    task_id: str,
    work_dir: str | Path = DEFAULT_PRODUCT_WORK_DIR,
) -> dict[str, Any]:
    """Fetch the result of a previously triggered exploration and rebuild the full workspace payload.

    Called by the frontend after polling the discovery backend and detecting task completion.
    """
    context = _pending_exploration_cache.pop(task_id, None)
    if context is None:
        raise ValueError(f"exploration task {task_id} not found in pending cache (expired or already completed)")

    exploration_runtime = _complete_workspace_exploration_runtime(
        task_id=task_id,
        scenario_id=context["scenario_id"],
        question_text=context["effective_question"],
        route_decision=context["route_decision"],
        runtime_status=context["runtime_status"],
        final_decision=context["final_decision"],
        failure_reason=context["failure_reason"],
        parser_status=context["parser_bundle"]["parser_status"],
        missing_fact_keys=context["parser_bundle"]["missing_fact_keys"],
        fact_sheet=context["parser_bundle"]["fact_sheet"],
        documents=context["documents"],
        matched_rule_id=context["matched_rule_id"],
        source_rule_ids=context["source_rule_ids"],
        fallback_rule_ids=context["fallback_rule_ids"],
    )

    parser_bundle = context["parser_bundle"]
    task_context = context["task_context"]
    runtime_result = context["runtime_result"]
    super_agent_assets = context["super_agent_assets"]
    final_answer = context["final_answer"]
    answer_engine = context["answer_engine"]
    super_agent_result = context["super_agent_result"]
    runtime_skill_spec_preview = super_agent_assets["runtime_skill_spec_preview"]
    runtime_skill_artifact = super_agent_assets["runtime_skill_artifact"]
    super_agent_handoff = super_agent_assets["super_agent_handoff"]

    if runtime_result.route_decision == "exploration" and runtime_skill_artifact is None:
        provisional_assets = _prepare_exploration_provisional_assets(
            exploration_runtime=exploration_runtime,
            work_dir=work_dir,
            trace_id=context["trace_id"],
            effective_question=context["effective_question"],
            task_context=task_context,
            parser_bundle=parser_bundle,
            super_agent_max_turns=context["super_agent_max_turns"],
            super_agent_backend=context["super_agent_backend"],
            coding_agent_check_command=context["coding_agent_check_command"],
            coding_agent_review_with_agent=context["coding_agent_review_with_agent"],
            coding_agent_provider=context["coding_agent_provider"],
        )
        if provisional_assets["runtime_skill_artifact"] is not None and provisional_assets["super_agent_handoff"] is not None:
            runtime_skill_spec_preview = provisional_assets["runtime_skill_spec_preview"]
            runtime_skill_artifact = provisional_assets["runtime_skill_artifact"]
            super_agent_handoff = provisional_assets["super_agent_handoff"]
            agent_result = _run_workspace_super_agent(
                runtime_skill_artifact=runtime_skill_artifact,
                super_agent_handoff=super_agent_handoff,
                run_live_super_agent=context["run_live_super_agent"],
                kimi_client=context.get("kimi_client"),
                effective_question=context["effective_question"],
                work_dir=work_dir,
                task_context=task_context,
                parser_bundle=parser_bundle,
                super_agent_max_turns=context["super_agent_max_turns"],
                effective_kimi_client=context["effective_kimi_client"],
                super_agent_backend=context["super_agent_backend"],
                coding_agent_check_command=context["coding_agent_check_command"],
                coding_agent_review_with_agent=context["coding_agent_review_with_agent"],
                coding_agent_provider=context["coding_agent_provider"],
                final_answer=final_answer,
            )
            final_answer = agent_result[0] if isinstance(agent_result, tuple) else (agent_result or final_answer)
            answer_engine = agent_result[1] if isinstance(agent_result, tuple) and len(agent_result) > 1 else answer_engine
            super_agent_result = agent_result[2] if isinstance(agent_result, tuple) and len(agent_result) > 2 else super_agent_result or agent_result

    if runtime_result.route_decision == "exploration" and _looks_like_placeholder_exploration_answer(final_answer):
        provisional_answer = _build_exploration_provisional_answer(
            question_text=context["effective_question"],
            exploration_runtime=exploration_runtime,
        )
        if provisional_answer:
            final_answer = provisional_answer
            answer_engine = "runtime"

    feedback_defaults = _build_workspace_feedback_defaults(
        runtime_result=runtime_result,
        final_decision=context["final_decision"],
        final_answer=final_answer,
        answer_engine=answer_engine,
        parser_bundle=parser_bundle,
        scenario_id=context["scenario_id"],
        exploration_runtime=exploration_runtime,
    )

    solution_view = _build_workspace_solution_view(
        question_text=context["effective_question"],
        documents=context["documents"],
        evidence_packets=context["evidence_packets"],
        parser_bundle=parser_bundle,
        trace_payload=context["trace_payload"],
        final_decision=context["final_decision"],
        final_answer=final_answer,
        answer_engine=answer_engine,
        route_decision=runtime_result.route_decision,
        runtime_result=runtime_result,
        feedback_defaults=feedback_defaults,
    )
    orchestration_view = build_orchestration_view(
        question_packet_preview=parser_bundle["question_packet_preview"],
        trace_payload=context["trace_payload"],
        route_decision=runtime_result.route_decision,
        final_decision=context["final_decision"],
        documents=context["documents"],
        evidence_refs=context["evidence_packets"],
        exploration_runtime=exploration_runtime,
    )
    solution_view["orchestration"] = orchestration_view

    embedding_backend = context["embedding_backend"]
    feedback_payload = _build_workspace_feedback_payload(
        feedback_defaults=feedback_defaults,
        effective_question=context["effective_question"],
        parser_bundle=parser_bundle,
        task_context=task_context,
        document_parse_result=context["document_parse_result"],
        exploration_runtime=exploration_runtime,
        runtime_result=runtime_result,
        trace_payload=context["trace_payload"],
        embedding_backend=embedding_backend,
        runtime_skill_spec_preview=runtime_skill_spec_preview,
        answer_engine=answer_engine,
    )

    exploration_links = _build_exploration_links(exploration_runtime)

    return {
        "exploration_runtime": exploration_runtime,
        "exploration_links": exploration_links,
        "final_answer": final_answer,
        "answer_engine": answer_engine,
        "final_decision": context["final_decision"],
        "feedback_defaults": feedback_defaults,
        "solution_view": solution_view,
        "orchestration_view": orchestration_view,
        "feedback_payload": feedback_payload,
        "runtime_skill_spec_preview": runtime_skill_spec_preview,
        "runtime_skill_artifact": runtime_skill_artifact,
        "super_agent_handoff": super_agent_handoff,
        "super_agent_result": super_agent_result,
    }
